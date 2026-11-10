"""Retrieval-Augmented Generation (RAG) for business documents.

Phase 1 uses a local NumPy vector index with deterministic hash embeddings when
no embedding API is configured.  The interface is intentionally compatible with
ChromaDB/FAISS-style stores so one can be swapped in later without changing the
UI.  PDF support uses ``pypdf`` when installed; DOCX support uses
``python-docx`` when installed.

Document answers are always labelled separately from dataset calculations and
include source references.  If no LLM is configured, the system returns a
strict extractive answer built from retrieved sentences instead of fabricating
one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import json
import re
from typing import Any, Iterable

from retailmind.ai.provider import AIProvider, cosine, local_embed


class RAGError(ValueError):
    """A user-facing document ingestion error."""


@dataclass
class RAGSource:
    doc_name: str
    chunk_index: int
    score: float
    excerpt: str

    def label(self) -> str:
        return f"{self.doc_name} · chunk {self.chunk_index + 1} · relevance {self.score:.2f}"

    def to_dict(self) -> dict[str, Any]:
        return {"doc_name": self.doc_name, "chunk_index": self.chunk_index, "score": self.score, "excerpt": self.excerpt}


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


class RAGStore:
    """A small, transparent vector store held in the Streamlit session."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.chunks: list[Chunk] = []

    # ---- ingestion ----------------------------------------------------
    def add_document(self, name: str, content: bytes, provider: AIProvider | None = None) -> int:
        text = extract_text(name, content)
        text = clean_text(text)
        if len(text) < 20:
            raise RAGError("The document does not contain enough readable text.")
        pieces = chunk_text(text)
        if not pieces:
            raise RAGError("The document could not be split into readable chunks.")
        embeddings = None
        if provider is not None and provider.available:
            embeddings = provider.embed(pieces)
        if not embeddings:
            embeddings = local_embed(pieces)
        self.remove_document(name)
        for index, (piece, embedding) in enumerate(zip(pieces, embeddings)):
            self.chunks.append(Chunk(doc_name=name, chunk_index=index, text=piece, embedding=embedding))
        self.documents[name] = {"name": name, "characters": len(text), "chunks": len(pieces)}
        return len(pieces)

    def remove_document(self, name: str) -> bool:
        before = len(self.chunks)
        self.chunks = [chunk for chunk in self.chunks if chunk.doc_name != name]
        self.documents.pop(name, None)
        return len(self.chunks) != before

    def clear(self) -> None:
        self.documents = {}
        self.chunks = []

    # ---- retrieval ----------------------------------------------------
    def search(self, query: str, top_k: int = 4) -> list[tuple[float, Chunk]]:
        if not self.chunks or not query.strip():
            return []
        vector = local_embed([query])[0]
        scored = [(cosine(vector, chunk.embedding), chunk) for chunk in self.chunks]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [(score, chunk) for score, chunk in scored[: max(1, top_k)] if score > 0.02]

    def answer(self, query: str, provider: AIProvider | None = None, top_k: int = 4) -> RAGAnswer:
        matches = self.search(query, top_k=top_k)
        if not matches:
            return RAGAnswer(
                "No relevant content was found in the uploaded documents. Add a document or rephrase the question.",
                note="Nothing was invented.",
            )
        sources = [
            RAGSource(doc_name=chunk.doc_name, chunk_index=chunk.chunk_index, score=score, excerpt=chunk.text[:280])
            for score, chunk in matches
        ]
        context_blocks = []
        for index, (score, chunk) in enumerate(matches, start=1):
            context_blocks.append(f"[{index}] Source: {chunk.doc_name} (chunk {chunk.chunk_index + 1})\n{chunk.text}")
        context = "\n\n".join(context_blocks)

        if provider is not None and provider.available:
            try:
                text = provider.chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You answer questions using ONLY the supplied document context. "
                                "Cite sources as [1], [2] etc. If the answer is not present, say "
                                "\"The uploaded documents do not contain that information.\" "
                                "Never invent facts, figures or sources."
                            ),
                        },
                        {"role": "user", "content": f"Document context:\n{context}\n\nQuestion: {query}"},
                    ],
                    temperature=0.1,
                    max_tokens=600,
                )
                return RAGAnswer(text, sources=sources, used_llm=True, note="Generated from retrieved document context.")
            except Exception:
                pass

        # Extractive fallback: real retrieval, no fabrication.
        sentences = _rank_sentences(query, [chunk.text for _score, chunk in matches])
        if not sentences:
            return RAGAnswer(
                "The uploaded documents were retrieved but do not appear to contain a direct answer. Review the sources below.",
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
                {"doc_name": chunk.doc_name, "chunk_index": chunk.chunk_index, "text": chunk.text, "embedding": chunk.embedding}
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
            )
            for item in payload.get("chunks") or []
        ]
        return store


# ---- text extraction ---------------------------------------------------
def extract_text(name: str, content: bytes) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except Exception:
            raise RAGError("PDF support requires the optional 'pypdf' package. Install it with: pip install pypdf") from None
        try:
            reader = PdfReader(BytesIO(content))
            return "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:
            raise RAGError(f"Could not read the PDF: {type(exc).__name__}") from None
    if lower.endswith(".docx"):
        try:
            from docx import Document
        except Exception:
            raise RAGError("DOCX support requires the optional 'python-docx' package. Install it with: pip install python-docx") from None
        try:
            document = Document(BytesIO(content))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        except Exception as exc:
            raise RAGError(f"Could not read the DOCX file: {type(exc).__name__}") from None
    if lower.endswith(".json"):
        try:
            payload = json.loads(content.decode("utf-8-sig", errors="replace"))
            return json.dumps(payload, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise RAGError("The document encoding could not be read.")


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    """Split text into overlapping chunks on paragraph/sentence boundaries."""
    if not text:
        return []
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= size:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= size:
            current = paragraph
        else:
            start = 0
            while start < len(paragraph):
                piece = paragraph[start : start + size]
                chunks.append(piece.strip())
                start += max(1, size - overlap)
            current = ""
    if current:
        chunks.append(current)
    # Add overlap between consecutive chunks for retrieval continuity.
    if len(chunks) > 1 and overlap > 0:
        blended: list[str] = []
        for index, chunk in enumerate(chunks):
            if index == 0:
                blended.append(chunk)
            else:
                tail = chunks[index - 1][-overlap:]
                blended.append(f"{tail}\n{chunk}".strip())
        chunks = blended
    return [chunk for chunk in chunks if chunk.strip()]


def _rank_sentences(query: str, chunks: Iterable[str], limit: int = 3) -> list[str]:
    query_tokens = set(re.findall(r"[a-z0-9]+", query.lower())) - {"the", "a", "an", "is", "are", "of", "to", "in", "on", "what", "which", "how", "and", "or", "for", "our", "we", "do", "does"}
    scored: list[tuple[int, str]] = []
    for chunk in chunks:
        for sentence in re.split(r"(?<=[.!?])\s+", chunk):
            sentence = sentence.strip()
            if len(sentence) < 30:
                continue
            tokens = set(re.findall(r"[a-z0-9]+", sentence.lower()))
            score = len(query_tokens & tokens)
            if score:
                scored.append((score, sentence))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[str] = []
    for _score, sentence in scored:
        if sentence not in selected:
            selected.append(sentence)
        if len(selected) >= limit:
            break
    return selected
