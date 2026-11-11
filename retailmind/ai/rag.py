"""Retrieval-Augmented Generation (RAG) for business documents.

The store keeps a local, deterministic vector index (feature hashing) so
retrieval works without any external service.  When an LLM/embedding provider
is configured it is used for embeddings and grounded answer generation; the
provider is never required and no answer is ever fabricated.

Key properties:
* heading-aware, configurable chunking with document/chunk/page metadata;
* hybrid retrieval (vector similarity + lexical coverage) with reranking and a
  calibrated rejection threshold, so irrelevant documents are not presented as
  evidence;
* an explicit no-answer response when the uploaded documents do not support a
  question;
* JSON serialization so the index survives a Python service restart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import hashlib
import json
import os
import re
from typing import Any, Iterable

from retailmind.ai.provider import AIProvider, cosine, local_embed

NO_ANSWER = "The requested information was not found in the uploaded documents."

# Retrieval thresholds are deliberately conservative.  A weak match is worse
# than an honest no-answer, because it invites fabricated citations.
MIN_RELEVANCE = 0.16
CANDIDATE_POOL = 12

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on", "for",
    "and", "or", "what", "which", "how", "many", "much", "does", "do", "did",
    "our", "we", "i", "you", "it", "its", "this", "that", "with", "by", "from",
    "as", "at", "be", "has", "have", "had", "can", "could", "should", "would",
    "please", "tell", "me", "about", "there", "their", "according",
}


class RAGError(ValueError):
    """A user-facing document ingestion error."""


def _chunk_settings() -> tuple[int, int]:
    try:
        size = max(200, min(int(os.getenv("RETAILMIND_RAG_CHUNK_SIZE", "900")), 4000))
    except ValueError:
        size = 900
    try:
        overlap = max(0, min(int(os.getenv("RETAILMIND_RAG_CHUNK_OVERLAP", "120")), size // 2))
    except ValueError:
        overlap = 120
    return size, overlap


@dataclass
class RAGSource:
    doc_name: str
    chunk_index: int
    score: float
    excerpt: str
    page: int | None = None
    chunk_id: str = ""
    doc_id: str = ""
    heading: str = ""

    def label(self) -> str:
        page = f" · page {self.page}" if self.page else ""
        return f"{self.doc_name}{page} · chunk {self.chunk_index + 1} · relevance {self.score:.2f}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_name": self.doc_name,
            "chunk_index": self.chunk_index,
            "chunk_id": self.chunk_id or f"chunk-{self.chunk_index + 1}",
            "doc_id": self.doc_id,
            "page": self.page,
            "heading": self.heading,
            "score": round(self.score, 4),
            "excerpt": self.excerpt,
            "citation": self.label(),
        }


@dataclass
class RAGAnswer:
    text: str
    sources: list[RAGSource] = field(default_factory=list)
    used_llm: bool = False
    note: str = ""
    verified_retrieval: bool = True


@dataclass
class Chunk:
    doc_name: str
    chunk_index: int
    text: str
    embedding: list[float] = field(default_factory=list)
    page: int | None = None
    heading: str = ""
    doc_id: str = ""

    @property
    def chunk_id(self) -> str:
        return f"{self.doc_id or self.doc_name}:{self.chunk_index}"


def _terms(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9][a-z0-9.%-]*", text.lower()) if token not in _STOPWORDS}


def _lexical_score(query_terms: set[str], text: str) -> float:
    if not query_terms:
        return 0.0
    chunk_terms = _terms(text)
    if not chunk_terms:
        return 0.0
    return len(query_terms & chunk_terms) / len(query_terms)


class RAGStore:
    """A transparent, per-workspace vector store with hybrid retrieval."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.chunks: list[Chunk] = []

    # ---- ingestion ----------------------------------------------------
    def add_document(
        self,
        name: str,
        content: bytes | str,
        provider: AIProvider | None = None,
        *,
        document_id: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> int:
        if isinstance(content, str):
            content = content.encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        existing = self.documents.get(name)
        if existing and existing.get("sha256") == digest:
            # Duplicate upload: keep the existing index, do not duplicate chunks.
            return int(existing.get("chunks") or 0)

        pages = extract_pages(name, content)
        text = clean_text("\n\n".join(page_text for _page, page_text in pages if page_text))
        if len(text) < 20:
            raise RAGError("The document does not contain enough readable text.")
        size, overlap = _chunk_settings()
        size = chunk_size or size
        overlap = chunk_overlap if chunk_overlap is not None else overlap
        pieces = chunk_documents(text, pages, size=size, overlap=overlap)
        if not pieces:
            raise RAGError("The document could not be split into readable chunks.")

        doc_id = document_id or digest[:16]
        texts = [piece["text"] for piece in pieces]
        embeddings = None
        if provider is not None and provider.available:
            embeddings = provider.embed(texts)
        embedding_kind = "provider" if embeddings else "local"
        if not embeddings:
            embeddings = local_embed(texts)

        self.remove_document(name)
        for index, (piece, embedding) in enumerate(zip(pieces, embeddings)):
            self.chunks.append(
                Chunk(
                    doc_name=name,
                    chunk_index=index,
                    text=piece["text"],
                    embedding=embedding,
                    page=piece["page"],
                    heading=piece["heading"],
                    doc_id=doc_id,
                )
            )
        self.documents[name] = {
            "name": name,
            "characters": len(text),
            "chunks": len(pieces),
            "doc_id": doc_id,
            "sha256": digest,
            "pages": len({page for page, _text in pages if page is not None}) or None,
            "embedding": embedding_kind,
            "status": "indexed",
            "chunk_size": size,
            "chunk_overlap": overlap,
        }
        return len(pieces)

    def remove_document(self, name: str) -> bool:
        before = len(self.chunks)
        self.chunks = [chunk for chunk in self.chunks if chunk.doc_name != name]
        self.documents.pop(name, None)
        return len(self.chunks) != before

    def clear(self) -> None:
        self.documents = {}
        self.chunks = []

    def has_duplicate(self, content: bytes | str, name: str | None = None) -> str | None:
        if isinstance(content, str):
            content = content.encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        for doc_name, document in self.documents.items():
            if document.get("sha256") == digest:
                return doc_name
        return None

    # ---- retrieval ----------------------------------------------------
    def search(self, query: str, top_k: int = 4, *, min_score: float = MIN_RELEVANCE) -> list[tuple[float, Chunk]]:
        if not self.chunks or not query.strip():
            return []
        query_terms = _terms(query)
        vector = local_embed([query])[0]
        scored: list[tuple[float, Chunk]] = []
        for chunk in self.chunks:
            similarity = max(0.0, cosine(vector, chunk.embedding))
            lexical = _lexical_score(query_terms, chunk.text)
            score = 0.55 * lexical + 0.45 * similarity
            # Exact phrase / figure matches are strong evidence.
            normalised_query = re.sub(r"\s+", " ", query.strip().lower())
            exact_phrase = len(normalised_query) >= 5 and normalised_query in re.sub(r"\s+", " ", chunk.text.lower())
            if exact_phrase:
                score += 0.12
            if chunk.heading and _terms(chunk.heading) & query_terms:
                score += 0.04
            # Reject weak evidence: a passage that shares only a generic word
            # (for example "annual" in a title) must not become a citation.
            if lexical < 0.5 and not exact_phrase and similarity < 0.45:
                score *= 0.35
            scored.append((min(score, 1.0), chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        candidates = scored[:CANDIDATE_POOL]
        # Rerank by lexical evidence so the most specific passage is cited first.
        candidates.sort(
            key=lambda item: (
                _lexical_score(query_terms, item[1].text) * 0.6 + item[0] * 0.4,
                item[0],
            ),
            reverse=True,
        )
        return [(score, chunk) for score, chunk in candidates[: max(1, top_k)] if score >= min_score]

    def diagnose(self, query: str, top_k: int = 5) -> dict[str, Any]:
        """Return retrieval scores for debugging, without exposing full content."""
        if not self.chunks:
            return {"chunks": 0, "results": []}
        query_terms = _terms(query)
        vector = local_embed([query])[0]
        rows = []
        for chunk in self.chunks:
            similarity = max(0.0, cosine(vector, chunk.embedding))
            lexical = _lexical_score(query_terms, chunk.text)
            rows.append(
                {
                    "doc_name": chunk.doc_name,
                    "chunk_index": chunk.chunk_index,
                    "page": chunk.page,
                    "vector": round(similarity, 4),
                    "lexical": round(lexical, 4),
                    "score": round(0.55 * lexical + 0.45 * similarity, 4),
                }
            )
        rows.sort(key=lambda row: row["score"], reverse=True)
        return {"chunks": len(self.chunks), "threshold": MIN_RELEVANCE, "results": rows[:top_k]}

    def answer(
        self,
        query: str,
        provider: AIProvider | None = None,
        top_k: int = 4,
        history: list[dict[str, str]] | None = None,
    ) -> RAGAnswer:
        if not self.chunks:
            return RAGAnswer(
                "No relevant content was found in the uploaded documents. Add a document or rephrase the question.",
                note="Nothing was invented.",
            )
        matches = self.search(query, top_k=top_k)
        if not matches:
            return RAGAnswer(
                f"The uploaded documents do not contain information about that question. {NO_ANSWER}",
                sources=[],
                note="No retrieved passage met the relevance threshold; nothing was invented.",
            )

        sources = [
            RAGSource(
                doc_name=chunk.doc_name,
                chunk_index=chunk.chunk_index,
                score=score,
                excerpt=chunk.text[:320],
                page=chunk.page,
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                heading=chunk.heading,
            )
            for score, chunk in matches
        ]
        context_blocks = []
        for index, (_score, chunk) in enumerate(matches, start=1):
            location = f", page {chunk.page}" if chunk.page else ""
            heading = f" — {chunk.heading}" if chunk.heading else ""
            context_blocks.append(
                f"[{index}] {chunk.doc_name}{location}, chunk {chunk.chunk_index + 1}{heading}\n{chunk.text}"
            )
        context = "\n\n".join(context_blocks)

        if provider is not None and provider.available:
            messages: list[dict[str, str]] = [
                {
                    "role": "system",
                    "content": (
                        "You are a document question-answering assistant. Answer using ONLY the "
                        "supplied context. Cite supporting sources as [1], [2] etc. after each claim. "
                        f'If the context does not contain the answer, reply exactly: "{NO_ANSWER}" '
                        "Do not use outside knowledge. Never invent names, figures, dates, policies or sources."
                    ),
                }
            ]
            for turn in (history or [])[-6:]:
                if turn.get("role") in {"user", "assistant"} and turn.get("content"):
                    messages.append({"role": turn["role"], "content": str(turn["content"])[:2000]})
            messages.append(
                {"role": "user", "content": f"Document context:\n{context}\n\nQuestion: {query}"}
            )
            try:
                text = provider.chat(messages, temperature=0.0, max_tokens=800)
                note = "Generated from retrieved document context."
                if NO_ANSWER.lower() in text.lower() or "not found in the uploaded documents" in text.lower():
                    note = "The model reported that the uploaded documents do not contain the answer."
                return RAGAnswer(text, sources=sources, used_llm=True, note=note)
            except Exception:
                # Fall through to the honest extractive answer; never fabricate.
                pass

        # Extractive fallback: real retrieval, no fabrication.
        sentences = _rank_sentences(query, [chunk.text for _score, chunk in matches])
        if not sentences:
            return RAGAnswer(
                f"The retrieved passages do not contain a direct answer. {NO_ANSWER}",
                sources=sources,
                note="Extractive retrieval only; no LLM configured.",
            )
        answer = " ".join(sentences)
        return RAGAnswer(
            answer,
            sources=sources,
            used_llm=False,
            note="Extractive answer from retrieved document text (no LLM configured).",
        )

    # ---- serialization ------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "documents": self.documents,
            "chunks": [
                {
                    "doc_name": chunk.doc_name,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "embedding": chunk.embedding,
                    "page": chunk.page,
                    "heading": chunk.heading,
                    "doc_id": chunk.doc_id,
                }
                for chunk in self.chunks
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RAGStore":
        store = cls()
        payload = payload or {}
        store.documents = dict(payload.get("documents") or {})
        store.chunks = [
            Chunk(
                doc_name=str(item.get("doc_name") or "document"),
                chunk_index=int(item.get("chunk_index") or 0),
                text=str(item.get("text") or ""),
                embedding=[float(value) for value in (item.get("embedding") or [])],
                page=int(item["page"]) if item.get("page") is not None else None,
                heading=str(item.get("heading") or ""),
                doc_id=str(item.get("doc_id") or ""),
            )
            for item in payload.get("chunks") or []
        ]
        return store

    def save(self, path: str) -> None:
        """Persist the index atomically so a restart can recover it."""
        import tempfile

        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=directory or ".", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self.to_dict(), stream)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path: str) -> "RAGStore":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as stream:
                return cls.from_dict(json.load(stream))
        except (OSError, json.JSONDecodeError):
            return cls()


# ---- text extraction ---------------------------------------------------
def _extract_pdf(content: bytes) -> list[tuple[int | None, str]]:
    try:
        from pypdf import PdfReader
    except Exception:
        raise RAGError("PDF support requires the optional 'pypdf' package. Install it with: pip install pypdf") from None
    try:
        reader = PdfReader(BytesIO(content))
        pages = [(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
    except Exception as exc:
        raise RAGError(f"Could not read the PDF: {type(exc).__name__}") from None
    if any(text.strip() for _page, text in pages):
        return pages
    # A scanned PDF has no selectable text. OCR is optional: it runs only when
    # both Python packages and the Tesseract executable are available.
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except Exception:
        raise RAGError(
            "This PDF has no selectable text. Scanned-PDF OCR requires the optional "
            "'pytesseract' and 'pdf2image' packages plus the Tesseract executable."
        ) from None
    try:
        images = convert_from_bytes(content, dpi=200)
        ocr_pages = [(index + 1, pytesseract.image_to_string(image)) for index, image in enumerate(images)]
    except Exception as exc:
        raise RAGError(f"Scanned-PDF OCR failed: {type(exc).__name__}") from None
    if not any(text.strip() for _page, text in ocr_pages):
        raise RAGError("OCR found no readable text in this scanned PDF.")
    return ocr_pages


def _extract_docx(content: bytes) -> list[tuple[int | None, str]]:
    try:
        from docx import Document
    except Exception:
        raise RAGError("DOCX support requires the optional 'python-docx' package. Install it with: pip install python-docx") from None
    try:
        document = Document(BytesIO(content))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return [(None, "\n".join(parts))]
    except Exception as exc:
        raise RAGError(f"Could not read the DOCX file: {type(exc).__name__}") from None


def _extract_tabular(name: str, content: bytes) -> list[tuple[int | None, str]]:
    import pandas as pd

    stream = BytesIO(content)
    if name.lower().endswith(".csv"):
        frame = pd.read_csv(stream)
        return [(None, frame.to_csv(index=False))]
    workbook = pd.ExcelFile(stream)
    pages: list[tuple[int | None, str]] = []
    for position, sheet in enumerate(workbook.sheet_names, start=1):
        frame = pd.read_excel(workbook, sheet_name=sheet)
        pages.append((position, f"Sheet: {sheet}\n{frame.to_csv(index=False)}"))
    return pages


def extract_pages(name: str, content: bytes) -> list[tuple[int | None, str]]:
    """Extract text with page-level metadata where the format supports it."""
    lower = name.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf(content)
    if lower.endswith(".docx"):
        return _extract_docx(content)
    if lower.endswith(".xlsx") or lower.endswith(".xls") or lower.endswith(".xlsm"):
        try:
            return _extract_tabular(name, content)
        except Exception as exc:
            raise RAGError(f"Could not read the spreadsheet: {type(exc).__name__}") from None
    if lower.endswith(".csv"):
        try:
            return _extract_tabular(name, content)
        except Exception as exc:
            raise RAGError(f"Could not read the CSV file: {type(exc).__name__}") from None
    if lower.endswith(".json"):
        try:
            payload = json.loads(content.decode("utf-8-sig", errors="replace"))
            return [(None, json.dumps(payload, ensure_ascii=False, indent=2))]
        except json.JSONDecodeError:
            pass
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return [(None, content.decode(encoding))]
        except UnicodeDecodeError:
            continue
    raise RAGError("The document encoding could not be read.")


def extract_text(name: str, content: bytes) -> str:
    return "\n\n".join(text for _page, text in extract_pages(name, content) if text)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_HEADING = re.compile(r"^(?:#{1,6}\s+.+|[A-Z][A-Za-z0-9 &/,\-()]{2,70}:?)$")


def chunk_documents(
    text: str,
    pages: Iterable[tuple[int | None, str]] | None = None,
    *,
    size: int = 900,
    overlap: int = 120,
) -> list[dict[str, Any]]:
    """Split extracted pages into overlapping, heading-aware chunks.

    Each chunk keeps its page number and nearest heading so citations can point
    to a precise location.  Chunks never span a page boundary.
    """
    result: list[dict[str, Any]] = []
    sources = list(pages) if pages else [(None, text)]
    for page, page_text in sources:
        page_text = clean_text(page_text or "")
        if not page_text:
            continue
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", page_text) if paragraph.strip()]
        if not paragraphs:
            continue
        current_heading = ""
        buffer = ""
        for paragraph in paragraphs:
            looks_like_heading = (
                len(paragraph) <= 80
                and "\n" not in paragraph
                and not paragraph.endswith(".")
                and bool(_HEADING.match(paragraph))
            )
            if looks_like_heading:
                current_heading = paragraph.lstrip("# ").strip()
            candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
            if len(candidate) <= size:
                buffer = candidate
                continue
            if buffer:
                result.append({"text": buffer, "page": page, "heading": current_heading})
            if len(paragraph) <= size:
                buffer = paragraph
            else:
                start = 0
                while start < len(paragraph):
                    piece = paragraph[start : start + size]
                    result.append({"text": piece.strip(), "page": page, "heading": current_heading})
                    start += max(1, size - overlap)
                buffer = ""
        if buffer:
            result.append({"text": buffer, "page": page, "heading": current_heading})
    if overlap > 0 and len(result) > 1:
        for index in range(1, len(result)):
            if result[index]["page"] != result[index - 1]["page"]:
                continue
            tail = result[index - 1]["text"][-overlap:]
            result[index]["text"] = f"{tail}\n{result[index]['text']}".strip()
    return [chunk for chunk in result if chunk["text"].strip()]


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    """Backwards-compatible text-only chunking API."""
    return [chunk["text"] for chunk in chunk_documents(text, [(None, text)], size=size, overlap=overlap)]


def _rank_sentences(query: str, chunks: Iterable[str], limit: int = 3) -> list[str]:
    query_tokens = _terms(query)
    scored: list[tuple[float, str]] = []
    for chunk in chunks:
        # Split on lines and real sentence boundaries.  Do not split after
        # abbreviations such as "Rs." before a number.
        for sentence in re.split(r"\n+|(?<=[.!?])\s+(?=[A-Z][a-z])", chunk):
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue
            tokens = _terms(sentence)
            overlap = len(query_tokens & tokens)
            if not overlap:
                continue
            score = overlap / max(len(query_tokens), 1) + (0.2 if query.lower() in sentence.lower() else 0)
            scored.append((score, sentence))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[str] = []
    for _score, sentence in scored:
        if sentence not in selected:
            selected.append(sentence)
        if len(selected) >= limit:
            break
    return selected
