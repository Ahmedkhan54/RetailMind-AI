"""Local FastAPI adapter for the existing RetailMind Python analytics modules.

This adapter is additive: the Streamlit entry point and its session workflow are
left untouched. Uploaded file metadata and bytes use the existing user-scoped
MySQL and filesystem services; parsed frames are cached in process memory.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
import secrets
import time
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import pandas as pd
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.gzip import GZipMiddleware

from analytics import build_insights, calculate_kpis, grouped_performance, monthly_summary, prepare_data, safe_ratio
from retailmind.alerts import Alert, NotificationPreferences, SEVERITY_ORDER, detect_alerts, send_alert_digest, send_alert_email, send_test_email
from retailmind.cleaning import DEFAULT_OPTIONS, analyse_cleaning, apply_cleaning
from retailmind.exports import executive_pdf, markdown_report, workbook_bytes
from retailmind.forecasting import forecast_dataset
from retailmind.inventory import build_inventory_recommendations
from retailmind.powerbi import build_pbip, validate_pbip
from retailmind.segmentation import segment_customers
from data_sources import detect_column_mapping, duplicate_source_columns, profile_schema, read_uploaded_file
from retailmind.ai.chat import answer_question
from retailmind.ai.provider import get_provider
from retailmind.ai.rag import MIN_RELEVANCE, RAGError, RAGStore
from retailmind.config import get_ai_config, state_dir
from retailmind.schema import infer_schema
from src.analytics.enterprise import scenario_projection
from src.business.goals import goal_progress
from threading import RLock
from src.auth.api import auth_service, database_connection, require_authenticated_user, router as account_router
from src.auth.service import AuthenticationError, UserProfile
from src.storage.uploads import UploadStorage, UploadStorageError

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm"}
DATASET_LIMIT = 8


@dataclass
class DatasetRecord:
    owner_id: int
    filename: str
    frame: pd.DataFrame
    mapping: dict[str, str | None]
    created_at: Any | None = None
    schema: Any | None = None
    # Derived data is immutable for a given mapping. Caching it avoids reparsing
    # and re-normalising the same rows for every dashboard/analytics request.
    canonical: pd.DataFrame | None = None
    canonical_mapping_key: tuple[tuple[str, str | None], ...] | None = None
    inventory_cache: dict[tuple[Any, ...], Any] = field(default_factory=dict)
    detail_metadata: dict[str, Any] | None = None
    visual_cache: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    segmentation_cache: dict[int | None, Any] = field(default_factory=dict)
    cleaning_metadata: dict[str, Any] | None = None
    overview_cache: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)


DATASETS: OrderedDict[str, DatasetRecord] = OrderedDict()
RAG_STORES: dict[int, RAGStore] = {}
RAG_LOCK = RLock()
API_TOKEN = os.environ.get("RETAILMIND_API_TOKEN")
app = FastAPI(title="RetailMind AI Python API", version="0.1.0")
app.include_router(account_router)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def response_diagnostics(request, call_next):
    """Expose server timing and keep account-scoped responses out of caches."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
    if request.url.path.startswith("/api/") and request.url.path not in {"/api/health", "/api/ready"}:
        response.headers["Cache-Control"] = "private, no-store"
    return response


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    if API_TOKEN and not secrets.compare_digest(authorization or "", f"Bearer {API_TOKEN}"):
        raise HTTPException(status_code=401, detail="A valid backend token is required.")


def get_dataset(dataset_id: str, user_id: int) -> DatasetRecord:
    record = DATASETS.get(dataset_id)
    if record is not None:
        if record.owner_id != user_id:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        return record

    try:
        stored = auth_service().get_uploaded_file(user_id, dataset_id)
        content = UploadStorage.from_environment(Path(__file__).resolve().parent).read(
            user_id, str(stored["storage_key"]), str(stored["file_sha256"])
        )
        frame = read_uploaded_file(content, str(stored["original_filename"]))
    except AuthenticationError as error:
        raise HTTPException(status_code=404, detail="Dataset not found.") from error
    except (UploadStorageError, ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail="The saved dataset is unavailable or failed validation.") from error

    record = DatasetRecord(
        owner_id=user_id,
        filename=str(stored["original_filename"]),
        frame=frame,
        mapping=detect_column_mapping(frame.columns),
        created_at=stored.get("created_at"),
    )
    DATASETS[dataset_id] = record
    while len(DATASETS) > DATASET_LIMIT:
        DATASETS.popitem(last=False)
    return record


def json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def schema_for(record: DatasetRecord):
    """Infer a dataset's schema once per process instead of on every request."""
    if record.schema is None:
        record.schema = infer_schema(record.frame)
    return record.schema


def canonical_frame(record: DatasetRecord) -> pd.DataFrame | None:
    required = {"order_id", "order_date", "category", "product_name", "city", "sales", "profit"}
    if not required.issubset({key for key, value in record.mapping.items() if value}):
        return None
    mapping_key = tuple(sorted((key, value) for key, value in record.mapping.items() if value))
    if record.canonical is not None and record.canonical_mapping_key == mapping_key:
        return record.canonical
    renamed = record.frame.rename(columns={source: target for target, source in record.mapping.items() if source})
    try:
        prepared = prepare_data(renamed)
    except (KeyError, ValueError):
        return None
    record.canonical = prepared
    record.canonical_mapping_key = mapping_key
    return prepared


def rows_for_dimension(frame: pd.DataFrame | None, dimension: str) -> list[dict[str, Any]]:
    if frame is None or dimension not in frame.columns:
        return []
    return json_records(grouped_performance(frame, dimension).head(8))


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "retailmind-python", "storage": "MySQL metadata + user-scoped files", "datasets": len(DATASETS)}


@app.get("/api/ready")
def readiness() -> JSONResponse:
    """Readiness probe that verifies the database path without leaking details.

    This endpoint is intentionally unauthenticated for load balancers, but it
    performs a real check of the configured MySQL/TiDB connection. The response
    never includes the host, user, password, CA path, or exception text.
    """
    connection = None
    cursor = None
    headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
    try:
        connection = database_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        if cursor.fetchone() is None:
            raise RuntimeError("The database readiness query returned no row.")
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "service": "retailmind-python",
                "database": "unreachable",
                "message": "Database readiness check failed.",
            },
            headers={**headers, "Retry-After": "5"},
        )
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
    return JSONResponse(
        content={"status": "ready", "service": "retailmind-python", "database": "reachable", "datasets": len(DATASETS)},
        headers=headers,
    )


@app.get("/api/datasets", dependencies=[Depends(require_api_token)])
def list_datasets(user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    try:
        files = auth_service().list_uploaded_files(user.id)
    except AuthenticationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "datasets": [
            {
                "id": str(item["id"]),
                "filename": item["original_filename"],
                "file_type": item["file_type"],
                "rows": int(item["row_count"]),
                "size_bytes": int(item["size_bytes"]),
                "created_at": item["created_at"],
                "validation_status": item["validation_status"],
            }
            for item in files
        ]
    }


@app.get("/api/datasets/history", dependencies=[Depends(require_api_token)])
def upload_history(user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    try:
        return {"history": auth_service().list_upload_history(user.id)}
    except AuthenticationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/datasets/{dataset_id}", dependencies=[Depends(require_api_token)])
def dataset_detail(dataset_id: str, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    if record.detail_metadata is None:
        missing = record.frame.isna().sum()
        record.detail_metadata = {
            "dataset_id": dataset_id,
            "filename": record.filename,
            "created_at": record.created_at,
            "row_count": int(len(record.frame)),
            "column_count": int(len(record.frame.columns)),
            "columns": [str(column) for column in record.frame.columns],
            "preview": json_records(record.frame.head(5)),
            "profile": profile_schema(record.frame),
            "quality": {
                "missing_cells": int(missing.sum()),
                "columns_with_missing_values": int((missing > 0).sum()),
                "duplicate_rows": int(record.frame.duplicated().sum()),
            },
        }
    return {
        **record.detail_metadata,
        "mapping": record.mapping,
    }


class DatasetMappingRequest(BaseModel):
    mapping: dict[str, str | None]


class CleaningOptionsRequest(BaseModel):
    options: dict[str, bool] = Field(default_factory=dict)


@app.put("/api/datasets/{dataset_id}/mapping", dependencies=[Depends(require_api_token)])
def update_dataset_mapping(
    dataset_id: str,
    payload: DatasetMappingRequest,
    user: UserProfile = Depends(require_authenticated_user),
) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    unknown_fields = set(payload.mapping) - set(record.mapping)
    unknown_columns = {column for column in payload.mapping.values() if column is not None} - set(record.frame.columns)
    selected_columns = [column for column in payload.mapping.values() if column is not None]
    if unknown_fields:
        raise HTTPException(status_code=422, detail="The mapping contains unsupported business fields.")
    if unknown_columns:
        raise HTTPException(status_code=422, detail="The mapping references a column that is not in this dataset.")
    if len(selected_columns) != len(set(selected_columns)):
        raise HTTPException(status_code=422, detail="Each source column can be assigned to only one business field.")

    record.mapping = {**record.mapping, **payload.mapping}
    return {
        "mapping": record.mapping,
        "persistence": "process-memory",
        "notes": ["Mapping changes apply to this API process; the original upload is unchanged."],
    }


@app.get("/api/datasets/{dataset_id}/cleaning", dependencies=[Depends(require_api_token)])
def dataset_cleaning_review(
    dataset_id: str,
    user: UserProfile = Depends(require_authenticated_user),
) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    if record.cleaning_metadata is None:
        schema = schema_for(record)
        cleaned, report = apply_cleaning(record.frame, schema)
        record.cleaning_metadata = {
            "columns": [str(column) for column in record.frame.columns],
            "domain_label": schema.domain_label,
            "options": DEFAULT_OPTIONS,
            "suggestions": [suggestion.to_dict() for suggestion in analyse_cleaning(record.frame, schema)],
            "preview": json_records(cleaned.head(5)),
            "report": report.to_dict(),
            "original_preserved": True,
        }
    return record.cleaning_metadata


@app.post("/api/datasets/{dataset_id}/cleaning", dependencies=[Depends(require_api_token)])
def export_cleaned_dataset(
    dataset_id: str,
    payload: CleaningOptionsRequest,
    user: UserProfile = Depends(require_authenticated_user),
) -> Response:
    record = get_dataset(dataset_id, user.id)
    unknown_options = set(payload.options) - set(DEFAULT_OPTIONS)
    if unknown_options:
        raise HTTPException(status_code=422, detail="The request contains unsupported cleaning options.")

    schema = schema_for(record)
    cleaned, report = apply_cleaning(record.frame, schema, payload.options)
    stem = "".join(character for character in os.path.splitext(os.path.basename(record.filename))[0] if character.isalnum() or character in "-_").strip("-_") or "dataset"
    summary = json.dumps({
        "rows_before": report.rows_before,
        "rows_after": report.rows_after,
        "applied": report.applied,
        "warnings": report.warnings,
        "original_preserved": report.original_preserved,
    }, separators=(",", ":"))
    return Response(
        content=cleaned.to_csv(index=False).encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{stem}-cleaned.csv"',
            "X-Cleaning-Report": summary,
        },
    )


@app.delete("/api/datasets/{dataset_id}", dependencies=[Depends(require_api_token)])
def delete_dataset(dataset_id: str, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    try:
        stored = auth_service().get_uploaded_file(user.id, dataset_id)
        storage = UploadStorage.from_environment(Path(__file__).resolve().parent)
        storage.delete_and_forget(
            user.id,
            str(stored["storage_key"]),
            lambda: auth_service().delete_uploaded_file(user.id, dataset_id),
        )
    except AuthenticationError as error:
        raise HTTPException(status_code=404, detail="Dataset not found.") from error
    except UploadStorageError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    DATASETS.pop(dataset_id, None)
    return {"ok": True}


@app.post("/api/upload", dependencies=[Depends(require_api_token)])
async def upload_dataset(
    file: UploadFile = File(...),
    user: UserProfile = Depends(require_authenticated_user),
) -> dict[str, Any]:
    filename = file.filename or ""
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Upload a CSV or Excel file (.csv, .xlsx, .xls, .xlsm).")

    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The existing upload limit is 25 MB.")
    if not content:
        raise HTTPException(status_code=400, detail="The selected file is empty.")

    duplicates = duplicate_source_columns(content, filename)
    if duplicates:
        raise HTTPException(status_code=422, detail=f"Duplicate column names must be resolved first: {', '.join(duplicates)}")
    try:
        frame = read_uploaded_file(content, filename)
    except (ValueError, OSError, ImportError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if frame.empty:
        raise HTTPException(status_code=422, detail="The file contains no data rows.")

    mapping = detect_column_mapping(frame.columns)
    dataset_id = str(uuid4())
    storage = UploadStorage.from_environment(Path(__file__).resolve().parent)
    try:
        stored = storage.store_and_record(
            user.id,
            filename,
            content,
            lambda upload: auth_service().create_uploaded_file(
                user.id,
                dataset_id,
                upload.original_filename,
                upload.file_type,
                upload.sha256,
                upload.row_count,
                upload.size_bytes,
                upload.storage_key,
            ),
        )
    except UploadStorageError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AuthenticationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    try:
        auth_service().record_upload(user.id, filename, stored.file_type, stored.sha256, stored.row_count, "valid")
    except AuthenticationError as error:
        try:
            storage.delete_and_forget(
                user.id,
                stored.storage_key,
                lambda: auth_service().delete_uploaded_file(user.id, dataset_id),
            )
        except (AuthenticationError, UploadStorageError):
            pass
        raise HTTPException(status_code=503, detail=str(error)) from error

    DATASETS[dataset_id] = DatasetRecord(owner_id=user.id, filename=filename, frame=frame, mapping=mapping)
    while len(DATASETS) > DATASET_LIMIT:
        DATASETS.popitem(last=False)

    profile = profile_schema(frame)
    missing = frame.isna().sum()
    return {
        "dataset_id": dataset_id,
        "filename": filename,
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "columns": [str(column) for column in frame.columns],
        "preview": json_records(frame.head(5)),
        "mapping": mapping,
        "profile": profile,
        "quality": {
            "missing_cells": int(missing.sum()),
            "columns_with_missing_values": int((missing > 0).sum()),
            "duplicate_rows": int(frame.duplicated().sum()),
        },
        "storage": "persistent",
    }


@app.get("/api/goals/progress/{dataset_id}", dependencies=[Depends(require_api_token)])
def goal_progress_for_dataset(dataset_id: str, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    frame = canonical_frame(record)
    if frame is None:
        return {"available": False, "goals": [], "notes": ["Map sales, profit, and order date columns to calculate goal progress."]}
    try:
        goals = auth_service().list_goals(user.id)
    except AuthenticationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"available": True, "goals": [goal_progress(goal, frame) for goal in goals], "notes": []}


@app.get("/api/dashboard/overview/{dataset_id}", dependencies=[Depends(require_api_token)])
def dashboard_overview(
    dataset_id: str,
    user: UserProfile = Depends(require_authenticated_user),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    cache_key = (
        tuple(sorted((key, value) for key, value in record.mapping.items() if value)),
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
    )
    cached = record.overview_cache.get(cache_key)
    if cached is not None:
        return cached
    source_frame, _filters = filter_export_frame(record, date_from, date_to)
    filtered_record = DatasetRecord(
        owner_id=record.owner_id,
        filename=record.filename,
        frame=source_frame,
        mapping=record.mapping,
        created_at=record.created_at,
    )
    frame = canonical_frame(filtered_record)
    if frame is None:
        return {
            "dataset_id": dataset_id,
            "dataset_name": record.filename,
            "available": False,
            "row_count": int(len(source_frame)),
            "kpis": None,
            "missing_fields": [
                field for field in ("order_id", "order_date", "category", "product_name", "city", "sales", "profit")
                if not record.mapping.get(field)
            ],
            "sales_by_month": [],
            "category_sales": [],
            "top_products": [],
            "city_performance": [],
            "recent_transactions": [],
            "insights": [],
        }

    kpis = calculate_kpis(frame)
    raw_mapping = record.mapping
    customer_column = raw_mapping.get("customer")
    product_column = raw_mapping.get("product_name")
    kpis["total_customers"] = int(source_frame[customer_column].nunique(dropna=True)) if customer_column else None
    kpis["total_products"] = int(source_frame[product_column].nunique(dropna=True)) if product_column else None

    monthly = monthly_summary(frame).rename(columns={"month": "date"})
    categories = rows_for_dimension(frame, "category")
    products = rows_for_dimension(frame, "product_name")
    cities = rows_for_dimension(frame, "city")
    transaction_columns = [column for column in ("order_id", "order_date", "product_name", "city", "sales", "profit") if column in frame]
    transactions = frame.sort_values("order_date", ascending=False).loc[:, transaction_columns].head(8)
    payload = {
        "dataset_id": dataset_id,
        "dataset_name": record.filename,
        "available": True,
        "row_count": int(len(frame)),
        "kpis": kpis,
        "missing_fields": [],
        "sales_by_month": json_records(monthly),
        "category_sales": categories,
        "top_products": products,
        "city_performance": cities,
        "recent_transactions": json_records(transactions),
        "insights": build_insights(frame, {"sales_change": None}, dimensions={"category", "product_name"}),
    }
    if len(record.overview_cache) >= 8:
        record.overview_cache.pop(next(iter(record.overview_cache)))
    record.overview_cache[cache_key] = payload
    return payload


class ChatRequest(BaseModel):
    dataset_id: str = Field(min_length=12, max_length=128)
    question: str = Field(min_length=1, max_length=2000)


@app.post("/api/ai/chat", dependencies=[Depends(require_api_token)])
def business_chat(payload: ChatRequest, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    record = get_dataset(payload.dataset_id, user.id)
    schema = schema_for(record)
    response = answer_question(payload.question.strip(), record.frame, schema)
    return {
        "text": response.text,
        "verified": response.verified,
        "sources": response.sources,
        "followups": response.followups,
        "note": response.note,
    }


class RAGQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)


def rag_store_path(user_id: int) -> Path:
    return state_dir() / "rag" / f"user-{int(user_id)}.json"


def get_rag_store(user_id: int) -> RAGStore:
    """Return the user's index, recovering it from disk after a restart."""
    with RAG_LOCK:
        store = RAG_STORES.get(user_id)
        if store is None:
            store = RAGStore.load(str(rag_store_path(user_id)))
            RAG_STORES[user_id] = store
        return store


def persist_rag_store(user_id: int, store: RAGStore) -> None:
    try:
        store.save(str(rag_store_path(user_id)))
        for document in store.documents.values():
            document["status"] = "indexed"
    except OSError:
        # Indexing still works in memory; status is reported honestly below.
        for document in store.documents.values():
            document["status"] = "indexed (not persisted)"


@app.get("/api/ai/rag/documents", dependencies=[Depends(require_api_token)])
def list_rag_documents(user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    store = get_rag_store(user.id)
    with RAG_LOCK:
        documents = sorted(store.documents.values(), key=lambda item: str(item["name"]).casefold())
        chunk_count = len(store.chunks)
    return {
        "documents": documents,
        "chunks": chunk_count,
        "storage": "persistent-disk",
        "retrieval": {"mode": "hybrid lexical + vector", "min_relevance": MIN_RELEVANCE},
    }


@app.get("/api/ai/rag/status", dependencies=[Depends(require_api_token)])
def rag_status(user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    store = get_rag_store(user.id)
    config = get_ai_config().public_status()
    with RAG_LOCK:
        chunk_count = len(store.chunks)
        documents = len(store.documents)
    return {
        "documents": documents,
        "chunks": chunk_count,
        "persistence": str(rag_store_path(user.id)),
        "retrieval": {"mode": "hybrid lexical + vector", "min_relevance": MIN_RELEVANCE},
        "generation": config,
    }


@app.post("/api/ai/rag/documents", dependencies=[Depends(require_api_token)])
async def add_rag_document(
    file: UploadFile = File(...),
    user: UserProfile = Depends(require_authenticated_user),
) -> dict[str, Any]:
    filename = file.filename or ""
    suffix = os.path.splitext(filename)[1].lower()
    if filename != os.path.basename(filename) or "/" in filename or "\\\\" in filename or len(filename) > 255:
        raise HTTPException(status_code=400, detail="Choose a document with a simple filename.")
    if suffix not in {".txt", ".md", ".csv", ".json", ".pdf", ".docx", ".xlsx", ".xls", ".xlsm"}:
        raise HTTPException(status_code=415, detail="Upload TXT, MD, CSV, JSON, PDF, DOCX, or an Excel workbook.")
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="RAG documents must be 5 MB or smaller.")
    if not content:
        raise HTTPException(status_code=400, detail="The selected document is empty.")
    store = get_rag_store(user.id)
    try:
        with RAG_LOCK:
            duplicate = store.has_duplicate(content)
            if duplicate:
                return {
                    "document": dict(store.documents[duplicate]),
                    "chunk_count": int(store.documents[duplicate].get("chunks") or 0),
                    "duplicate": True,
                    "message": f"This file is already indexed as {duplicate}.",
                }
            if filename not in store.documents and len(store.documents) >= 25:
                raise HTTPException(status_code=413, detail="A workspace can hold up to 25 RAG documents.")
            chunk_count = store.add_document(filename, content, provider=get_provider())
            document = dict(store.documents[filename])
            persist_rag_store(user.id, store)
            document = dict(store.documents[filename])
    except RAGError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "document": document,
        "chunk_count": chunk_count,
        "duplicate": False,
        "storage": "persistent-disk",
        "generation": get_ai_config().public_status(),
    }


@app.post("/api/ai/rag/documents/{document_name}/reindex", dependencies=[Depends(require_api_token)])
def reindex_rag_document(document_name: str, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    store = get_rag_store(user.id)
    provider = get_provider()
    with RAG_LOCK:
        if document_name not in store.documents:
            raise HTTPException(status_code=404, detail="Document not found.")
        chunks = [chunk for chunk in store.chunks if chunk.doc_name == document_name]
        if not chunks:
            raise HTTPException(status_code=422, detail="This document has no indexed text to rebuild.")
        texts = [chunk.text for chunk in chunks]
        embeddings = provider.embed(texts) if provider.available else None
        if not embeddings:
            from retailmind.ai.provider import local_embed

            embeddings = local_embed(texts)
            kind = "local"
        else:
            kind = "provider"
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        store.documents[document_name]["embedding"] = kind
        persist_rag_store(user.id, store)
    return {"ok": True, "document": document_name, "chunks": len(chunks), "embedding": kind}


@app.delete("/api/ai/rag/documents/{document_name}", dependencies=[Depends(require_api_token)])
def remove_rag_document(document_name: str, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    store = get_rag_store(user.id)
    with RAG_LOCK:
        removed = store.remove_document(document_name)
        if removed:
            persist_rag_store(user.id, store)
    if not removed:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"ok": True}


@app.post("/api/ai/rag", dependencies=[Depends(require_api_token)])
def rag_answer(payload: RAGQuestion, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    store = get_rag_store(user.id)
    history = [
        {"role": turn.get("role", "user"), "content": turn.get("content", "")}
        for turn in payload.history[-6:]
        if turn.get("content")
    ]
    with RAG_LOCK:
        answer = store.answer(payload.question.strip(), provider=get_provider(), history=history)
    return {
        "text": answer.text,
        "verified_retrieval": answer.verified_retrieval,
        "sources": [source.to_dict() for source in answer.sources],
        "note": answer.note,
        "used_llm": answer.used_llm,
        "generation": get_ai_config().public_status(),
    }


@app.get("/api/analytics/{dataset_id}/{dimension}", dependencies=[Depends(require_api_token)])
def analytics_breakdown(
    dataset_id: str,
    dimension: Literal["month", "category", "product_name", "city", "customer"],
    user: UserProfile = Depends(require_authenticated_user),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    source_frame, _filters = filter_export_frame(record, date_from, date_to)
    filtered_record = DatasetRecord(
        owner_id=record.owner_id,
        filename=record.filename,
        frame=source_frame,
        mapping=record.mapping,
        created_at=record.created_at,
    )
    frame = canonical_frame(filtered_record)
    if frame is None:
        return {"available": False, "rows": [], "notes": ["Map the required sales, profit, and date fields before using analytics."]}
    if dimension == "month":
        rows = json_records(monthly_summary(frame).rename(columns={"month": "date"}))
    elif dimension in frame.columns:
        rows = json_records(grouped_performance(frame, dimension).head(200))
    else:
        rows = []
    return {
        "available": bool(rows),
        "dimension": dimension,
        "rows": rows,
        "row_count": len(rows),
        "notes": [] if rows else [f"The uploaded file does not contain a usable {dimension.replace('_', ' ')} field."],
    }


def _visual_dimension_rows(frame: pd.DataFrame, dimension: str, limit: int = 50) -> list[dict[str, Any]]:
    """Aggregate one canonical dimension, ignoring blank labels."""
    if dimension not in frame.columns:
        return []
    usable = frame[frame[dimension].notna()]
    if usable.empty:
        return []
    return json_records(grouped_performance(usable, dimension).head(limit))


def _visual_filter_options(frame: pd.DataFrame, dimension: str, limit: int = 200) -> list[str]:
    """List real filter values ordered by their observed sales contribution."""
    if dimension not in frame.columns:
        return []
    values = frame[[dimension, "sales"]].dropna(subset=[dimension]).copy()
    values[dimension] = values[dimension].astype(str).str.strip()
    values = values[values[dimension] != ""]
    if values.empty:
        return []
    ordered = values.groupby(dimension)["sales"].sum().sort_values(ascending=False)
    return [str(value) for value in ordered.index[:limit]]


def _visual_month_dimension(frame: pd.DataFrame, dimension: str, limit: int = 8) -> list[dict[str, Any]]:
    """Return month-by-dimension sales for stacked, ribbon, and heatmap charts."""
    if dimension not in frame.columns:
        return []
    usable = frame.dropna(subset=["order_date"])
    usable = usable[usable[dimension].notna()]
    if usable.empty:
        return []
    totals = usable.groupby(dimension)["sales"].sum().sort_values(ascending=False).head(limit)
    usable = usable[usable[dimension].isin(totals.index)].copy()
    usable["month"] = usable["order_date"].dt.to_period("M").dt.to_timestamp()
    grouped = usable.groupby([dimension, "month"], as_index=False)[["sales", "profit"]].sum()
    grouped = grouped.rename(columns={"month": "date", dimension: "label"})
    return json_records(grouped.sort_values(["date", "sales"], ascending=[True, False]))


def _visual_cross_rows(
    frame: pd.DataFrame,
    row_dimension: str,
    column_dimension: str,
    row_limit: int = 10,
    column_limit: int = 12,
) -> list[dict[str, Any]]:
    """Return a real two-dimension cross-tab used by matrix and heatmap views."""
    if row_dimension not in frame.columns or column_dimension not in frame.columns:
        return []
    usable = frame.dropna(subset=[row_dimension, column_dimension])
    if usable.empty:
        return []
    row_totals = usable.groupby(row_dimension)["sales"].sum().sort_values(ascending=False).head(row_limit)
    column_totals = usable.groupby(column_dimension)["sales"].sum().sort_values(ascending=False).head(column_limit)
    usable = usable[usable[row_dimension].isin(row_totals.index) & usable[column_dimension].isin(column_totals.index)]
    if usable.empty:
        return []
    grouped = usable.groupby([row_dimension, column_dimension], as_index=False)[["sales", "profit"]].sum()
    grouped = grouped.rename(columns={row_dimension: "row_label", column_dimension: "col_label"})
    return json_records(grouped.sort_values("sales", ascending=False))


def _visual_histogram(values: pd.Series, bins: int = 12) -> list[dict[str, Any]]:
    """Build equal-width histogram bins from finite observed values."""
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    numeric = numeric[numeric.map(lambda value: math.isfinite(float(value)))]
    if numeric.empty:
        return []
    unique_count = int(numeric.nunique())
    if unique_count <= 1:
        value = float(numeric.iloc[0])
        return [{"bin_start": value, "bin_end": value, "count": int(numeric.size), "label": f"{value:,.0f}"}]
    binned = pd.cut(numeric, bins=min(bins, unique_count), duplicates="drop")
    counts = binned.value_counts().sort_index()
    rows: list[dict[str, Any]] = []
    for interval, count in counts.items():
        if int(count) <= 0:
            continue
        rows.append({
            "bin_start": float(interval.left),
            "bin_end": float(interval.right),
            "count": int(count),
            "label": f"{float(interval.left):,.0f} – {float(interval.right):,.0f}",
        })
    return rows


def _visual_box_rows(frame: pd.DataFrame, dimension: str, measure: str = "sales", limit: int = 8) -> list[dict[str, Any]]:
    """Summarise the observed distribution of a measure per dimension value."""
    if dimension not in frame.columns or measure not in frame.columns:
        return []
    usable = frame.dropna(subset=[dimension])
    if usable.empty:
        return []
    top = usable.groupby(dimension)[measure].sum().sort_values(ascending=False).head(limit)
    rows: list[dict[str, Any]] = []
    for key in top.index:
        values = pd.to_numeric(usable.loc[usable[dimension] == key, measure], errors="coerce").dropna()
        values = values[values.map(lambda value: math.isfinite(float(value)))]
        if values.empty:
            continue
        rows.append({
            "label": str(key),
            "min": float(values.min()),
            "q1": float(values.quantile(0.25)),
            "median": float(values.median()),
            "q3": float(values.quantile(0.75)),
            "max": float(values.max()),
            "mean": float(values.mean()),
            "count": int(values.size),
        })
    return rows


def _visual_pareto(product_rows: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    """Return product sales with cumulative contribution shares."""
    usable = [row for row in product_rows if row.get("product_name") and isinstance(row.get("sales"), (int, float))]
    total = sum(float(row["sales"]) for row in usable)
    if total <= 0:
        return []
    running = 0.0
    rows: list[dict[str, Any]] = []
    for row in usable[:limit]:
        running += float(row["sales"])
        rows.append({
            "label": str(row["product_name"]),
            "sales": float(row["sales"]),
            "share": float(row["sales"]) / total,
            "cumulative_share": running / total,
        })
    return rows


def _visual_waterfall(category_rows: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    """Show how each category contributes to total profit, including negatives."""
    usable = [row for row in category_rows if isinstance(row.get("profit"), (int, float))]
    if not usable:
        return []
    top = usable[:limit]
    rest = usable[limit:]
    if rest:
        top = top + [{
            "category": "Other",
            "profit": sum(float(row["profit"]) for row in rest),
            "sales": sum(float(row.get("sales") or 0) for row in rest),
        }]
    running = 0.0
    rows: list[dict[str, Any]] = []
    for row in top:
        start = running
        running += float(row["profit"])
        rows.append({
            "label": str(row.get("category") or "Unmapped"),
            "value": float(row["profit"]),
            "start": start,
            "end": running,
            "type": "increase" if float(row["profit"]) >= 0 else "decrease",
        })
    rows.append({"label": "Total profit", "value": running, "start": 0.0, "end": running, "type": "total"})
    return rows


def _visual_funnel(product_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Describe observed sales concentration across the leading products."""
    usable = [row for row in product_rows if isinstance(row.get("sales"), (int, float))]
    if not usable:
        return []
    total = sum(float(row["sales"]) for row in usable)
    if total <= 0:
        return []
    thresholds = [1, 3, 5, 10]
    stages: list[dict[str, Any]] = []
    running = 0.0
    added = 0
    for index, row in enumerate(usable, start=1):
        running += float(row["sales"])
        if index in thresholds or index == len(usable):
            label = f"Top {index} product{'s' if index != 1 else ''}" if index < len(usable) else f"All {len(usable)} products"
            stages.append({"stage": label, "value": running, "share": running / total, "products": index})
            added += 1
    return stages if added else []


def _visual_decomposition(category_rows: list[dict[str, Any]], product_rows: list[dict[str, Any]], limit: int = 6) -> dict[str, Any]:
    """Build a compact category-to-product decomposition tree from real totals."""
    total = sum(float(row.get("sales") or 0) for row in category_rows)
    children: list[dict[str, Any]] = []
    for category in category_rows[:limit]:
        name = str(category.get("category") or "Unmapped")
        products = [
            {"label": str(row.get("product_name")), "value": float(row.get("sales") or 0)}
            for row in product_rows
            if str(row.get("category") or "Unmapped") == name
        ][:5]
        children.append({
            "label": name,
            "value": float(category.get("sales") or 0),
            "children": products,
        })
    return {"label": "Total sales", "value": total, "children": children}


def _visual_influencers(category_rows: list[dict[str, Any]], overall_margin: float | None) -> list[dict[str, Any]]:
    """Rank dimensions by observed sales contribution and margin difference."""
    total = sum(float(row.get("sales") or 0) for row in category_rows)
    rows: list[dict[str, Any]] = []
    for row in category_rows[:10]:
        sales = float(row.get("sales") or 0)
        margin = row.get("margin")
        rows.append({
            "label": str(row.get("category") or "Unmapped"),
            "sales": sales,
            "profit": float(row.get("profit") or 0),
            "share": safe_ratio(sales, total),
            "margin": margin,
            "margin_delta": (float(margin) - overall_margin) if isinstance(margin, (int, float)) and overall_margin is not None else None,
        })
    return rows


@app.get("/api/visuals/{dataset_id}", dependencies=[Depends(require_api_token)])
def visual_analytics(
    dataset_id: str,
    user: UserProfile = Depends(require_authenticated_user),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category: str | None = Query(default=None, max_length=200),
    city: str | None = Query(default=None, max_length=200),
    region: str | None = Query(default=None, max_length=200),
) -> dict[str, Any]:
    """Return additive aggregates for every advanced chart type.

    All values are calculated from the same canonical frame used by the
    dashboard and analytics endpoints. No chart-specific sample data is added.
    """
    record = get_dataset(dataset_id, user.id)
    cache_key = (
        tuple(sorted((key, value) for key, value in record.mapping.items() if value)),
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
        (category or "").casefold(),
        (city or "").casefold(),
        (region or "").casefold(),
    )
    cached = record.visual_cache.get(cache_key)
    if cached is not None:
        return cached
    source_frame, _filters = filter_export_frame(record, date_from, date_to)
    filtered_record = DatasetRecord(
        owner_id=record.owner_id,
        filename=record.filename,
        frame=source_frame,
        mapping=record.mapping,
        created_at=record.created_at,
    )
    frame = canonical_frame(filtered_record)
    if frame is None:
        return {
            "available": False,
            "dataset_id": dataset_id,
            "dataset_name": record.filename,
            "filters": {"category": [], "city": [], "region": []},
            "notes": ["Map sales, profit, date, category, product, city, and order fields before using visual analytics."],
        }

    selected = {"category": category, "city": city, "region": region}
    option_frame = frame
    applied: dict[str, str] = {}
    for field, value in selected.items():
        if not value or value.casefold() == "all":
            continue
        if field not in frame.columns:
            raise HTTPException(status_code=422, detail=f"The uploaded file has no mapped {field} field to filter by.")
        mask = frame[field].astype("string").str.casefold() == value.casefold()
        frame = frame[mask]
        applied[field] = value

    if frame.empty:
        return {
            "available": False,
            "dataset_id": dataset_id,
            "dataset_name": record.filename,
            "filters": {"category": [], "city": [], "region": []},
            "applied_filters": applied,
            "row_count": 0,
            "matched_rows": 0,
            "filters": {
                "category": _visual_filter_options(option_frame, "category"),
                "city": _visual_filter_options(option_frame, "city"),
                "region": _visual_filter_options(option_frame, "region"),
            },
            "notes": ["No records match the selected filters."],
        }

    dimension_available = {
        name: name in frame.columns for name in ("category", "product_name", "city", "region", "customer", "order_id")
    }
    category_rows = _visual_dimension_rows(frame, "category", limit=100)
    product_rows = _visual_dimension_rows(frame, "product_name", limit=100)
    city_rows = _visual_dimension_rows(frame, "city", limit=100)
    region_rows = _visual_dimension_rows(frame, "region", limit=100)
    kpis = calculate_kpis(frame)
    for role, key in (("customer", "total_customers"), ("product_name", "total_products")):
        column = role if role in frame.columns else None
        kpis[key] = int(frame[column].nunique(dropna=True)) if column else None
    overall_margin = kpis.get("profit_margin") if isinstance(kpis.get("profit_margin"), (int, float)) else None

    payload = {
        "available": True,
        "dataset_id": dataset_id,
        "dataset_name": record.filename,
        "row_count": int(len(source_frame)),
        "matched_rows": int(len(frame)),
        "applied_filters": applied,
        "kpis": kpis,
        "dimensions": dimension_available,
        "filters": {
            "category": _visual_filter_options(option_frame, "category"),
            "city": _visual_filter_options(option_frame, "city"),
            "region": _visual_filter_options(option_frame, "region"),
        },
        "monthly": json_records(monthly_summary(frame).rename(columns={"month": "date"})),
        "categories": category_rows,
        "products": product_rows,
        "cities": city_rows,
        "regions": region_rows,
        "category_month": _visual_month_dimension(frame, "category"),
        "category_city": _visual_cross_rows(frame, "category", "city"),
        "region_month": _visual_month_dimension(frame, "region"),
        "product_category": [
            {
                "product_name": row.get("product_name"),
                "category": row.get("category"),
                "sales": row.get("sales"),
                "profit": row.get("profit"),
            }
            for row in product_rows
            if row.get("product_name") and row.get("category")
        ][:40],
        "histogram": {
            "sales": _visual_histogram(frame["sales"]),
            "profit": _visual_histogram(frame["profit"]),
        },
        "box": {
            "sales_by_category": _visual_box_rows(frame, "category", "sales"),
            "profit_by_category": _visual_box_rows(frame, "category", "profit"),
        },
        "scatter": json_records(
            frame[["sales", "profit"] + [name for name in ("category", "city", "product_name") if name in frame.columns]]
            .sample(n=min(400, len(frame)), random_state=42)
            .sort_values("sales", ascending=False)
        ),
        "pareto": _visual_pareto(product_rows),
        "waterfall": _visual_waterfall(category_rows),
        "funnel": _visual_funnel(product_rows),
        "decomposition": _visual_decomposition(category_rows, product_rows),
        "influencers": _visual_influencers(category_rows, overall_margin),
        "notes": [
            note
            for note in (
                "State-level map values use the mapped region field; city markers use a bundled coordinate gazetteer and never infer a location for an unknown city."
                if not region_rows else None,
                "Geographic values are only those present in the uploaded dataset; unmatched locations are listed rather than estimated."
                if region_rows or city_rows else None,
            )
            if note
        ],
    }
    if len(record.visual_cache) >= 8:
        record.visual_cache.pop(next(iter(record.visual_cache)))
    record.visual_cache[cache_key] = payload
    return payload


@app.get("/api/ai/insights/{dataset_id}", dependencies=[Depends(require_api_token)])
def business_insights(dataset_id: str, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    frame = canonical_frame(record)
    if frame is None:
        return {"available": False, "insights": [], "notes": ["Map the required retail columns to calculate business insights."]}
    insights = build_insights(frame, {"sales_change": None}, dimensions={"category", "product_name"})
    return {"available": True, "insights": insights, "notes": []}


ALERT_STATE_LOCK = RLock()
SEVERITY_LABELS = {"critical": "Critical", "warning": "High", "info": "Medium"}


def alert_state_path(user_id: int) -> Path:
    return state_dir() / "alerts" / f"user-{int(user_id)}.json"


def load_alert_state(user_id: int) -> dict[str, Any]:
    path = alert_state_path(user_id)
    if not path.exists():
        return {"datasets": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"datasets": {}}


def save_alert_state(user_id: int, state: dict[str, Any]) -> None:
    path = alert_state_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def humanize_scope(scope: str) -> tuple[str, str]:
    """Turn ``product_name:Office Chair`` into a readable label."""
    if not scope or ":" not in scope:
        return (scope or "Overall", "")
    dimension, value = scope.split(":", 1)
    labels = {
        "product_name": "Product", "category": "Category", "city": "City", "region": "Region",
        "customer": "Customer", "sales_rep": "Sales representative", "payment_method": "Payment method",
    }
    return (value.strip(), labels.get(dimension.strip(), dimension.replace("_", " ").title()))


def merged_alert_rows(user_id: int, dataset_id: str, alerts: list[Alert]) -> list[dict[str, Any]]:
    state = load_alert_state(user_id)
    stored = (state.get("datasets") or {}).get(dataset_id, {})
    rows: list[dict[str, Any]] = []
    for alert in alerts:
        entry = stored.get(alert.id, {})
        value, dimension = humanize_scope(alert.scope)
        row = asdict(alert)
        row.update({
            "status": entry.get("status", alert.status),
            "acknowledged_at": entry.get("updated_at", alert.acknowledged_at),
            "status_note": entry.get("note", ""),
            "severity_label": SEVERITY_LABELS.get(alert.severity, alert.severity.title()),
            "scope_label": value,
            "scope_dimension": dimension,
        })
        rows.append(row)
    rows.sort(key=lambda row: (SEVERITY_ORDER.get(str(row.get("severity")), 9), str(row.get("title"))))
    return rows


def effective_alert_preferences(user: UserProfile) -> NotificationPreferences:
    """Deployment SMTP settings with the account's enable/severity overrides."""
    preferences = NotificationPreferences.from_env()
    state = load_alert_state(user.id)
    overrides = state.get("preferences") or {}
    if isinstance(overrides.get("enabled"), bool):
        preferences.email_enabled = overrides["enabled"]
    if overrides.get("min_severity") in {"critical", "warning", "info"}:
        preferences.min_severity = overrides["min_severity"]
    if overrides.get("frequency") in {"instant", "daily"}:
        preferences.frequency = overrides["frequency"]
    if preferences.email_enabled and not preferences.recipients and user.email:
        preferences.recipients = (user.email,)
    return preferences


def dispatch_alert_emails(
    user_id: int,
    dataset_id: str,
    alerts: list[Alert],
    rows: list[dict[str, Any]],
    preferences: NotificationPreferences | None = None,
) -> dict[str, Any]:
    preferences = preferences or NotificationPreferences.from_env()
    if not preferences.configured():
        return {
            "enabled": preferences.email_enabled,
            "configured": False,
            "status": "not_configured",
            "missing": [
                name for name, present in (
                    ("RETAILMIND_ALERT_EMAIL_ENABLED", preferences.email_enabled),
                    ("RETAILMIND_ALERT_EMAIL_TO", bool(preferences.recipients)),
                    ("RETAILMIND_SMTP_HOST", bool(preferences.smtp_host)),
                    ("RETAILMIND_SMTP_FROM", bool(preferences.sender)),
                ) if not present
            ],
            "sent": [],
        }
    by_id = {alert.id: alert for alert in alerts}
    state = load_alert_state(user_id)
    dataset_state = (state.setdefault("datasets", {}).setdefault(dataset_id, {}))
    base_link = f"{(os.getenv('RETAILMIND_PUBLIC_ORIGIN') or 'http://localhost:3000').rstrip('/')}/smart-alerts"
    eligible: list[tuple[Alert, dict[str, Any], dict[str, Any]]] = []
    for row in rows:
        if row.get("severity") not in {"critical", "warning"}:
            continue
        if row.get("status") in {"dismissed", "resolved"}:
            continue
        alert = by_id.get(str(row.get("id")))
        if alert is None:
            continue
        entry = dataset_state.setdefault(alert.id, {})
        attempts = int(entry.get("delivery_attempts") or 0)
        if entry.get("notified_at") or attempts >= 3:
            continue
        eligible.append((alert, row, entry))
    if not eligible:
        return {"enabled": True, "configured": True, "status": "no_new_alerts", "sent": [], "failed": [], "max_attempts": 3}

    sent: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def record(alert: Alert, entry: dict[str, Any], delivery: str) -> None:
        entry["delivery"] = delivery
        entry["delivery_attempts"] = int(entry.get("delivery_attempts") or 0) + 1
        entry["last_attempt_at"] = now
        if delivery == "accepted_by_smtp":
            entry["notified_at"] = now
            entry.pop("last_delivery_error", None)
            sent.append({"alert_id": alert.id, "title": alert.title, "delivery": delivery})
        else:
            # A failed hand-off must remain retryable on a later check.
            entry["last_delivery_error"] = delivery
            failed.append({"alert_id": alert.id, "title": alert.title, "delivery": delivery})

    if preferences.frequency == "daily":
        today = now[:10]
        if state.get("last_digest_date") == today:
            return {"enabled": True, "configured": True, "status": "digest_already_sent", "sent": [], "failed": [], "max_attempts": 3}
        delivery = send_alert_digest([alert for alert, _row, _entry in eligible], preferences, base_link)
        for alert, _row, entry in eligible:
            record(alert, entry, delivery)
        if delivery == "accepted_by_smtp":
            state["last_digest_date"] = today
        save_alert_state(user_id, state)
        return {
            "enabled": True,
            "configured": True,
            "status": "digest_sent" if delivery == "accepted_by_smtp" else "failed",
            "sent": sent,
            "failed": failed,
            "max_attempts": 3,
        }

    for alert, _row, entry in eligible:
        record(alert, entry, send_alert_email(alert, preferences, f"{base_link}#alert-{alert.id}"))
    save_alert_state(user_id, state)
    status = "sent" if sent else "failed"
    return {"enabled": True, "configured": True, "status": status, "sent": sent, "failed": failed, "max_attempts": 3}


class AlertPreferenceRequest(BaseModel):
    enabled: bool
    min_severity: Literal["critical", "warning", "info"] = "warning"
    frequency: Literal["instant", "daily"] = "instant"


def _preference_payload(user: UserProfile) -> dict[str, Any]:
    preferences = effective_alert_preferences(user)
    return {
        "enabled": preferences.email_enabled,
        "configured": preferences.configured(),
        "smtp_ready": preferences.smtp_ready(),
        "min_severity": preferences.min_severity,
        "frequency": preferences.frequency,
        "recipient_count": len(preferences.recipients),
        "missing": [
            name for name, present in (
                ("RETAILMIND_ALERT_EMAIL_TO", bool(preferences.recipients)),
                ("RETAILMIND_SMTP_HOST", bool(preferences.smtp_host)),
                ("RETAILMIND_SMTP_FROM", bool(preferences.sender)),
            ) if not present
        ],
    }


@app.get("/api/ai/alerts/preferences", dependencies=[Depends(require_api_token)])
def get_alert_preferences(user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    return _preference_payload(user)


@app.post("/api/ai/alerts/email/test", dependencies=[Depends(require_api_token)])
def test_alert_email(user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    """Send one clearly-labelled test message to the signed-in account."""
    preferences = effective_alert_preferences(user)
    if not preferences.smtp_host or not preferences.sender:
        return {
            "ok": False,
            "status": "not_configured",
            "missing": [
                name for name, present in (
                    ("RETAILMIND_SMTP_HOST", bool(preferences.smtp_host)),
                    ("RETAILMIND_SMTP_FROM", bool(preferences.sender)),
                ) if not present
            ],
            "note": "Set the SMTP variables and restart the API before testing.",
        }
    delivery = send_test_email(preferences, user.email)
    return {
        "ok": delivery == "accepted_by_smtp",
        "status": delivery,
        "note": (
            "The SMTP server accepted the test message. Inbox delivery is not guaranteed."
            if delivery == "accepted_by_smtp"
            else "The SMTP server did not accept the test message. Check the server logs and configuration."
        ),
    }


@app.post("/api/ai/alerts/preferences", dependencies=[Depends(require_api_token)])
def set_alert_preferences(
    payload: AlertPreferenceRequest,
    user: UserProfile = Depends(require_authenticated_user),
) -> dict[str, Any]:
    with ALERT_STATE_LOCK:
        state = load_alert_state(user.id)
        state["preferences"] = {
            "enabled": payload.enabled,
            "min_severity": payload.min_severity,
            "frequency": payload.frequency,
        }
        save_alert_state(user.id, state)
    return _preference_payload(user)


@app.get("/api/ai/alerts/{dataset_id}", dependencies=[Depends(require_api_token)])
def business_alerts(dataset_id: str, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    alerts = detect_alerts(record.frame, schema_for(record))
    rows = merged_alert_rows(user.id, dataset_id, alerts)
    email_status = {"enabled": False, "configured": False, "status": "disabled", "sent": []}
    if os.getenv("RETAILMIND_ALERT_AUTO_EMAIL", "1").lower() in {"1", "true", "yes"}:
        try:
            email_status = dispatch_alert_emails(user.id, dataset_id, alerts, rows, effective_alert_preferences(user))
        except OSError:
            email_status = {"enabled": True, "configured": True, "status": "storage_error", "sent": []}
    return {
        "available": True,
        "alerts": rows,
        "count": len(rows),
        "severity_counts": {label: sum(1 for row in rows if row.get("severity_label") == label) for label in ("Critical", "High", "Medium")},
        "email": email_status,
    }


class AlertStatusRequest(BaseModel):
    action: Literal["acknowledge", "dismiss", "resolve", "reopen"]
    note: str = Field(default="", max_length=500)


@app.post("/api/ai/alerts/{dataset_id}/{alert_id}/status", dependencies=[Depends(require_api_token)])
def update_alert_status(
    dataset_id: str,
    alert_id: str,
    payload: AlertStatusRequest,
    user: UserProfile = Depends(require_authenticated_user),
) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    alerts = detect_alerts(record.frame, schema_for(record))
    if not any(alert.id == alert_id for alert in alerts):
        raise HTTPException(status_code=404, detail="This alert no longer matches the active dataset.")
    status = {"acknowledge": "acknowledged", "dismiss": "dismissed", "resolve": "resolved", "reopen": "new"}[payload.action]
    with ALERT_STATE_LOCK:
        state = load_alert_state(user.id)
        dataset_state = state.setdefault("datasets", {}).setdefault(dataset_id, {})
        entry = dataset_state.setdefault(alert_id, {})
        entry["status"] = status
        entry["note"] = payload.note
        entry["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_alert_state(user.id, state)
    return {"ok": True, "alert_id": alert_id, "status": status, "persistence": "disk"}


@app.get("/api/ai/alerts/email/status", dependencies=[Depends(require_api_token)])
def alert_email_status(user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    preferences = effective_alert_preferences(user)
    return {
        "enabled": preferences.email_enabled,
        "configured": preferences.configured(),
        "recipients": len(preferences.recipients),
        "min_severity": preferences.min_severity,
        "missing": [
            name for name, present in (
                ("RETAILMIND_ALERT_EMAIL_ENABLED", preferences.email_enabled),
                ("RETAILMIND_ALERT_EMAIL_TO", bool(preferences.recipients)),
                ("RETAILMIND_SMTP_HOST", bool(preferences.smtp_host)),
                ("RETAILMIND_SMTP_FROM", bool(preferences.sender)),
            ) if not present
        ],
        "note": "Email is sent only when the SMTP server accepts the message; delivery is never assumed.",
    }


@app.get("/api/segmentation/{dataset_id}", dependencies=[Depends(require_api_token)])
def customer_segmentation(
    dataset_id: str,
    user: UserProfile = Depends(require_authenticated_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=250),
    clusters: int | None = Query(default=None, ge=2, le=10),
    tag: str | None = Query(default=None, max_length=40),
    search: str | None = Query(default=None, max_length=120),
    cluster: int | None = Query(default=None, ge=0, le=20),
    sort: Literal["monetary", "recency", "frequency", "customer"] = "monetary",
) -> dict[str, Any]:
    # Support both HTTP calls and direct unit-test calls (whose unpassed
    # defaults are FastAPI Query objects rather than plain values).
    if not isinstance(tag, str):
        tag = None
    if not isinstance(search, str):
        search = None
    if not isinstance(cluster, int):
        cluster = None
    if not isinstance(clusters, int):
        clusters = None
    if sort not in {"monetary", "recency", "frequency", "customer"}:
        sort = "monetary"
    record = get_dataset(dataset_id, user.id)
    result = record.segmentation_cache.get(clusters)
    if result is None:
        result = segment_customers(record.frame, schema_for(record), clusters=clusters)
        if len(record.segmentation_cache) >= 4:
            record.segmentation_cache.pop(next(iter(record.segmentation_cache)))
        record.segmentation_cache[clusters] = result
    filtered = result.rfm
    if tag and "customer_tag" in filtered.columns:
        filtered = filtered[filtered["customer_tag"].astype("string").str.casefold() == tag.casefold()]
    if search and "customer_id" in filtered.columns:
        filtered = filtered[filtered["customer_id"].astype("string").str.contains(search, case=False, regex=False, na=False)]
    if cluster is not None and "cluster" in filtered.columns:
        filtered = filtered[filtered["cluster"] == cluster]
    sort_columns = {
        "monetary": ("monetary", False),
        "recency": ("recency", True),
        "frequency": ("frequency", False),
        "customer": ("customer_id", True),
    }
    sort_column, ascending = sort_columns[sort]
    if sort_column in filtered.columns:
        filtered = filtered.sort_values(sort_column, ascending=ascending)
    customers = filtered.iloc[offset : offset + limit]
    tags: dict[str, int] = {}
    if result.available and "customer_tag" in result.rfm.columns:
        tags = {str(key): int(value) for key, value in result.rfm["customer_tag"].value_counts().items()}
    return {
        "available": result.available,
        "summary": json_records(result.summary),
        "customers": json_records(customers),
        "customer_total": len(filtered),
        "base_total": len(result.rfm),
        "customer_offset": offset,
        "customer_limit": limit,
        "cluster_count": result.k,
        "silhouette": result.silhouette,
        "tags": tags,
        "tag_total": int(sum(tags.values())),
        "notes": result.notes,
    }


@app.get("/api/segmentation/{dataset_id}/export/{export_format}", dependencies=[Depends(require_api_token)])
def export_customer_segmentation(
    dataset_id: str,
    export_format: Literal["csv", "xlsx"],
    user: UserProfile = Depends(require_authenticated_user),
) -> Response:
    record = get_dataset(dataset_id, user.id)
    result = segment_customers(record.frame, schema_for(record))
    if not result.available:
        raise HTTPException(status_code=422, detail="Customer RFM export needs a usable customer, date, and revenue mapping.")

    stem = "".join(
        character
        for character in os.path.splitext(os.path.basename(record.filename))[0]
        if character.isalnum() or character in "-_"
    ).strip("-_") or "retailmind"
    if export_format == "csv":
        data = result.to_csv_bytes()
        filename, media_type = f"{stem}_customer_rfm.csv", "text/csv; charset=utf-8"
    else:
        data = result.to_excel_bytes()
        filename, media_type = f"{stem}_customer_rfm.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/inventory/{dataset_id}", dependencies=[Depends(require_api_token)])
def inventory_recommendations(
    dataset_id: str,
    user: UserProfile = Depends(require_authenticated_user),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    cache_key = (
        tuple(sorted((key, value) for key, value in record.mapping.items() if value)),
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
    )
    result = record.inventory_cache.get(cache_key)
    if result is None:
        frame, _filters = filter_export_frame(record, date_from, date_to)
        result = build_inventory_recommendations(frame, infer_schema(frame))
        if len(record.inventory_cache) >= 8:
            record.inventory_cache.pop(next(iter(record.inventory_cache)))
        record.inventory_cache[cache_key] = result
    return {
        "available": result.available,
        "recommendations": json_records(result.table.head(500)),
        "notes": result.notes,
        "assumptions": result.assumptions,
        "stock_available": result.stock_available,
    }


class ForecastRequest(BaseModel):
    dataset_id: str = Field(min_length=12, max_length=128)
    metric_role: Literal["revenue", "profit"] = "revenue"
    frequency: Literal["Daily", "Weekly", "Monthly"] = "Monthly"
    periods: int = Field(default=6, ge=1, le=365)
    method: Literal["Auto (backtest)", "Moving average", "Exponential smoothing", "Linear trend", "ARIMA / SARIMA"] = "Auto (backtest)"


@app.post("/api/forecast", dependencies=[Depends(require_api_token)])
def forecast(payload: ForecastRequest, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    record = get_dataset(payload.dataset_id, user.id)
    result = forecast_dataset(
        record.frame,
        schema_for(record),
        metric_role=payload.metric_role,
        frequency=payload.frequency,
        periods=payload.periods,
        method=payload.method,
    )
    return {
        "available": result.available,
        "metric": result.metric,
        "frequency": result.frequency,
        "method": result.method,
        "history": json_records(result.history),
        "forecast": json_records(result.forecast),
        "metrics": result.metrics,
        "notes": result.notes,
        "train_size": result.train_size,
        "test_size": result.test_size,
    }


class ScenarioRequest(BaseModel):
    dataset_id: str = Field(min_length=12, max_length=128)
    discount_shift_points: float = Field(default=0, ge=-100, le=100)
    margin_shift_points: float = Field(default=0, ge=-100, le=100)


@app.post("/api/scenarios/projection", dependencies=[Depends(require_api_token)])
def project_business_scenario(
    payload: ScenarioRequest,
    user: UserProfile = Depends(require_authenticated_user),
) -> dict[str, Any]:
    record = get_dataset(payload.dataset_id, user.id)
    sales_column = record.mapping.get("sales")
    profit_column = record.mapping.get("profit")
    if not sales_column or sales_column not in record.frame.columns or not profit_column or profit_column not in record.frame.columns:
        return {
            "available": False,
            "notes": ["Map both sales and profit fields to calculate a business scenario."],
        }

    paired_measures = pd.DataFrame({
        "sales": pd.to_numeric(record.frame[sales_column], errors="coerce"),
        "profit": pd.to_numeric(record.frame[profit_column], errors="coerce"),
    }).replace([float("inf"), float("-inf")], float("nan")).dropna()
    if paired_measures.empty:
        return {
            "available": False,
            "notes": ["The mapped sales and profit fields need at least one row with valid numeric values in both columns."],
        }

    total_sales = float(paired_measures["sales"].sum())
    total_profit = float(paired_measures["profit"].sum())
    projection = scenario_projection(
        total_sales,
        total_profit,
        payload.discount_shift_points,
        payload.margin_shift_points,
    )
    return {
        "available": True,
        "baseline_sales": total_sales,
        "baseline_profit": total_profit,
        **projection,
        "rows_used": int(len(paired_measures)),
        "rows_excluded": int(len(record.frame) - len(paired_measures)),
        "inputs": {
            "discount_shift_points": payload.discount_shift_points,
            "margin_shift_points": payload.margin_shift_points,
        },
        "notes": ["This transparent what-if applies the selected percentage-point shifts to observed totals; it is not a causal forecast."],
    }


def filter_export_frame(
    record: DatasetRecord,
    date_from: date | None,
    date_to: date | None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="The report start date must be on or before its end date.")
    if not date_from and not date_to:
        return record.frame, {}

    schema = schema_for(record)
    date_column = record.mapping.get("order_date") or schema.role_column("date") or (schema.dates[0] if schema.dates else None)
    if not date_column or date_column not in record.frame.columns:
        raise HTTPException(status_code=422, detail="A date column is required to apply a report date range.")

    dates = pd.to_datetime(record.frame[date_column], format="mixed", errors="coerce", utc=True)
    mask = dates.notna()
    if date_from:
        mask &= dates >= pd.Timestamp(date_from, tz="UTC")
    if date_to:
        mask &= dates < pd.Timestamp(date_to + timedelta(days=1), tz="UTC")
    filters = {
        key: value.isoformat()
        for key, value in (("date_from", date_from), ("date_to", date_to))
        if value is not None
    }
    return record.frame.loc[mask].copy(), filters


@app.get("/api/export/{dataset_id}/{export_format}", dependencies=[Depends(require_api_token)])
def export_dataset(
    dataset_id: str,
    export_format: Literal["csv", "xlsx", "pdf", "pbip", "md"],
    user: UserProfile = Depends(require_authenticated_user),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> Response:
    record = get_dataset(dataset_id, user.id)
    frame, filters = filter_export_frame(record, date_from, date_to)
    schema = infer_schema(frame)
    filtered_record = DatasetRecord(owner_id=record.owner_id, filename=record.filename, frame=frame, mapping=record.mapping, created_at=record.created_at)
    canonical = canonical_frame(filtered_record)
    stem = "".join(character for character in os.path.splitext(os.path.basename(record.filename))[0] if character.isalnum() or character in "-_").strip("-_") or "retailmind"

    if export_format == "csv":
        data = frame.to_csv(index=False).encode("utf-8-sig")
        filename, media_type = f"{stem}.csv", "text/csv; charset=utf-8"
    elif export_format == "xlsx":
        mapping = pd.DataFrame([{"field": key, "source column": value or "Not mapped"} for key, value in record.mapping.items()])
        quality = pd.DataFrame([{
            "rows": len(frame),
            "columns": len(frame.columns),
            "missing cells": int(frame.isna().sum().sum()),
            "columns with missing values": int(frame.isna().any().sum()),
            "duplicate rows": int(frame.duplicated().sum()),
        }])
        data = workbook_bytes({"Dataset": frame, "Field mapping": mapping, "Data quality": quality})
        filename, media_type = f"{stem}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif export_format == "md":
        bundle = markdown_report(frame, title=stem, filters=filters)
        data, filename, media_type = bundle.data, f"{stem}_report.md", bundle.mime
    elif export_format == "pdf":
        insights = build_insights(canonical, {"sales_change": None}) if canonical is not None else []
        alerts = detect_alerts(frame, schema)
        segmentation = segment_customers(frame, schema)
        forecast_result = forecast_dataset(frame, schema, metric_role="revenue", frequency="Monthly", periods=6)
        inventory = build_inventory_recommendations(frame, schema)
        bundle = executive_pdf(
            frame,
            schema,
            filename=stem,
            filters=filters,
            insights=insights,
            segmentation=segmentation,
            forecast=forecast_result,
            inventory=inventory,
            alerts=alerts,
        )
        data, media_type = bundle.data, bundle.mime
        extension = ".pdf" if media_type == "application/pdf" else ".txt"
        filename = f"{stem}_executive_summary{extension}"
    else:
        project = build_pbip(
            frame,
            schema,
            project_name=f"RetailMind {stem} Report",
            insights=build_insights(canonical, {"sales_change": None}) if canonical is not None else [],
            forecast_available=True,
            inventory_available=True,
        )
        errors = validate_pbip(project)
        if errors:
            raise HTTPException(status_code=422, detail={"message": "The PBIP project failed structural validation.", "errors": errors})
        data, filename, media_type = project.to_zip_bytes(), f"{stem}_pbip.zip", "application/zip"

    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
