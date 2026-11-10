"""Local FastAPI adapter for the existing RetailMind Python analytics modules.

This adapter is additive: the Streamlit entry point and its session workflow are
left untouched. Uploaded file metadata and bytes use the existing user-scoped
MySQL and filesystem services; parsed frames are cached in process memory.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
import json
import os
import secrets
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import pandas as pd
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from analytics import build_insights, calculate_kpis, grouped_performance, monthly_summary, prepare_data
from retailmind.alerts import detect_alerts
from retailmind.cleaning import DEFAULT_OPTIONS, analyse_cleaning, apply_cleaning
from retailmind.exports import executive_pdf, markdown_report, workbook_bytes
from retailmind.forecasting import forecast_dataset
from retailmind.inventory import build_inventory_recommendations
from retailmind.powerbi import build_pbip, validate_pbip
from retailmind.segmentation import segment_customers
from data_sources import detect_column_mapping, duplicate_source_columns, profile_schema, read_uploaded_file
from retailmind.ai.chat import answer_question
from retailmind.ai.rag import RAGError, RAGStore
from retailmind.schema import infer_schema
from src.analytics.enterprise import scenario_projection
from src.business.goals import goal_progress
from threading import RLock
from src.auth.api import auth_service, require_authenticated_user, router as account_router
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


DATASETS: OrderedDict[str, DatasetRecord] = OrderedDict()
RAG_STORES: dict[int, RAGStore] = {}
RAG_LOCK = RLock()
API_TOKEN = os.environ.get("RETAILMIND_API_TOKEN")
app = FastAPI(title="RetailMind AI Python API", version="0.1.0")
app.include_router(account_router)


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


def canonical_frame(record: DatasetRecord) -> pd.DataFrame | None:
    required = {"order_id", "order_date", "category", "product_name", "city", "sales", "profit"}
    if not required.issubset({key for key, value in record.mapping.items() if value}):
        return None
    renamed = record.frame.rename(columns={source: target for target, source in record.mapping.items() if source})
    try:
        return prepare_data(renamed)
    except (KeyError, ValueError):
        return None


def rows_for_dimension(frame: pd.DataFrame | None, dimension: str) -> list[dict[str, Any]]:
    if frame is None or dimension not in frame.columns:
        return []
    return json_records(grouped_performance(frame, dimension).head(8))


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "retailmind-python", "storage": "MySQL metadata + user-scoped files", "datasets": len(DATASETS)}


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
    missing = record.frame.isna().sum()
    return {
        "dataset_id": dataset_id,
        "filename": record.filename,
        "created_at": record.created_at,
        "row_count": int(len(record.frame)),
        "column_count": int(len(record.frame.columns)),
        "columns": [str(column) for column in record.frame.columns],
        "preview": json_records(record.frame.head(5)),
        "mapping": record.mapping,
        "profile": profile_schema(record.frame),
        "quality": {
            "missing_cells": int(missing.sum()),
            "columns_with_missing_values": int((missing > 0).sum()),
            "duplicate_rows": int(record.frame.duplicated().sum()),
        },
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
    schema = infer_schema(record.frame)
    cleaned, report = apply_cleaning(record.frame, schema)
    return {
        "columns": [str(column) for column in record.frame.columns],
        "domain_label": schema.domain_label,
        "options": DEFAULT_OPTIONS,
        "suggestions": [suggestion.to_dict() for suggestion in analyse_cleaning(record.frame, schema)],
        "preview": json_records(cleaned.head(5)),
        "report": report.to_dict(),
        "original_preserved": True,
    }


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

    schema = infer_schema(record.frame)
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
    return {
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


class ChatRequest(BaseModel):
    dataset_id: str = Field(min_length=12, max_length=128)
    question: str = Field(min_length=1, max_length=2000)


@app.post("/api/ai/chat", dependencies=[Depends(require_api_token)])
def business_chat(payload: ChatRequest, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    record = get_dataset(payload.dataset_id, user.id)
    schema = infer_schema(record.frame)
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


def get_rag_store(user_id: int) -> RAGStore:
    with RAG_LOCK:
        return RAG_STORES.setdefault(user_id, RAGStore())


@app.get("/api/ai/rag/documents", dependencies=[Depends(require_api_token)])
def list_rag_documents(user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    store = get_rag_store(user.id)
    with RAG_LOCK:
        documents = sorted(store.documents.values(), key=lambda item: str(item["name"]).casefold())
    return {"documents": documents, "storage": "session-memory"}


@app.post("/api/ai/rag/documents", dependencies=[Depends(require_api_token)])
async def add_rag_document(
    file: UploadFile = File(...),
    user: UserProfile = Depends(require_authenticated_user),
) -> dict[str, Any]:
    filename = file.filename or ""
    suffix = os.path.splitext(filename)[1].lower()
    if filename != os.path.basename(filename) or "/" in filename or "\\\\" in filename or len(filename) > 255:
        raise HTTPException(status_code=400, detail="Choose a document with a simple filename.")
    if suffix not in {".txt", ".md", ".csv", ".json", ".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Upload TXT, MD, CSV, JSON, PDF, or DOCX documents.")
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="RAG documents must be 5 MB or smaller.")
    store = get_rag_store(user.id)
    try:
        with RAG_LOCK:
            if filename not in store.documents and len(store.documents) >= 25:
                raise HTTPException(status_code=413, detail="A workspace can hold up to 25 RAG documents per service session.")
            chunk_count = store.add_document(filename, content)
            document = dict(store.documents[filename])
    except RAGError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"document": document, "chunk_count": chunk_count, "storage": "session-memory"}


@app.delete("/api/ai/rag/documents/{document_name}", dependencies=[Depends(require_api_token)])
def remove_rag_document(document_name: str, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    store = get_rag_store(user.id)
    with RAG_LOCK:
        removed = store.remove_document(document_name)
    if not removed:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"ok": True}


@app.post("/api/ai/rag", dependencies=[Depends(require_api_token)])
def rag_answer(payload: RAGQuestion, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    store = get_rag_store(user.id)
    with RAG_LOCK:
        answer = store.answer(payload.question.strip())
    return {
        "text": answer.text,
        "verified_retrieval": answer.verified_retrieval,
        "sources": [source.to_dict() for source in answer.sources],
        "note": answer.note,
        "used_llm": answer.used_llm,
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


@app.get("/api/ai/insights/{dataset_id}", dependencies=[Depends(require_api_token)])
def business_insights(dataset_id: str, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    frame = canonical_frame(record)
    if frame is None:
        return {"available": False, "insights": [], "notes": ["Map the required retail columns to calculate business insights."]}
    insights = build_insights(frame, {"sales_change": None}, dimensions={"category", "product_name"})
    return {"available": True, "insights": insights, "notes": []}


@app.get("/api/ai/alerts/{dataset_id}", dependencies=[Depends(require_api_token)])
def business_alerts(dataset_id: str, user: UserProfile = Depends(require_authenticated_user)) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    alerts = detect_alerts(record.frame, infer_schema(record.frame))
    return {"available": True, "alerts": [asdict(alert) for alert in alerts], "count": len(alerts)}


@app.get("/api/segmentation/{dataset_id}", dependencies=[Depends(require_api_token)])
def customer_segmentation(
    dataset_id: str,
    user: UserProfile = Depends(require_authenticated_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=250),
) -> dict[str, Any]:
    record = get_dataset(dataset_id, user.id)
    result = segment_customers(record.frame, infer_schema(record.frame))
    customers = result.rfm.iloc[offset : offset + limit]
    return {
        "available": result.available,
        "summary": json_records(result.summary),
        "customers": json_records(customers),
        "customer_total": len(result.rfm),
        "customer_offset": offset,
        "customer_limit": limit,
        "cluster_count": result.k,
        "silhouette": result.silhouette,
        "notes": result.notes,
    }


@app.get("/api/segmentation/{dataset_id}/export/{export_format}", dependencies=[Depends(require_api_token)])
def export_customer_segmentation(
    dataset_id: str,
    export_format: Literal["csv", "xlsx"],
    user: UserProfile = Depends(require_authenticated_user),
) -> Response:
    record = get_dataset(dataset_id, user.id)
    result = segment_customers(record.frame, infer_schema(record.frame))
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
    frame, _filters = filter_export_frame(record, date_from, date_to)
    result = build_inventory_recommendations(frame, infer_schema(frame))
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
        infer_schema(record.frame),
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

    schema = infer_schema(record.frame)
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
