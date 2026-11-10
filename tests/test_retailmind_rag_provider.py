"""Tests for RAG ingestion, retrieval, citations and AI configuration safety."""

from __future__ import annotations

import importlib.util
import os
import unittest
from unittest import mock

from retailmind.ai.provider import cosine, extract_json, local_embed
from retailmind.ai.rag import (
    RAGError,
    RAGStore,
    chunk_text,
    clean_text,
    extract_text,
)
from retailmind.config import AIConfig, get_ai_config

POLICY = (
    "Refund policy. Customers may request a refund within 30 days of purchase.\n\n"
    "Shipping policy. Standard delivery takes five business days inside the country.\n\n"
    "Warranty policy. Electronics carry a twelve month manufacturer warranty.\n\n"
    "Privacy policy. Customer email addresses are stored securely and never sold.\n"
)


class RAGTests(unittest.TestCase):
    def test_text_extraction_and_chunking(self):
        text = extract_text("policy.txt", POLICY.encode("utf-8"))
        self.assertIn("Refund policy", text)
        chunks = chunk_text(text, size=120, overlap=20)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.strip() for chunk in chunks))
        self.assertIn("Warranty", " ".join(chunks))

    def test_clean_text_collapses_excess_whitespace(self):
        cleaned = clean_text("a  b\t\tc\n\n\n\nd")
        self.assertEqual(cleaned, "a b c\n\nd")

    def test_ingestion_search_and_citations(self):
        store = RAGStore()
        count = store.add_document("policy.txt", POLICY.encode("utf-8"))
        self.assertGreater(count, 0)
        self.assertIn("policy.txt", store.documents)

        matches = store.search("refund request window for a customer", top_k=3)
        self.assertTrue(matches)
        self.assertEqual(matches[0][1].doc_name, "policy.txt")
        self.assertTrue(matches[0][1].text)

        answer = store.answer("How many days does a customer have to request a refund?")
        self.assertFalse(answer.used_llm)
        self.assertIn("30 days", answer.text)
        self.assertTrue(answer.sources)
        self.assertEqual(answer.sources[0].doc_name, "policy.txt")
        self.assertTrue(answer.sources[0].excerpt)
        self.assertIn("extractive", answer.note.lower())

    def test_missing_answer_is_not_invented(self):
        store = RAGStore()
        store.add_document("policy.txt", POLICY.encode("utf-8"))
        answer = store.answer("What is the capital of France?")
        self.assertNotIn("Paris", answer.text)
        self.assertIn("do not", answer.text.lower())
        self.assertTrue(
            "nothing was invented" in answer.note.lower() or "no llm" in answer.note.lower()
        )

    def test_empty_store_returns_no_content_without_fabrication(self):
        store = RAGStore()
        answer = store.answer("What is the refund window?")
        self.assertIn("No relevant content", answer.text)
        self.assertEqual(answer.sources, [])
        self.assertEqual(answer.note, "Nothing was invented.")

    def test_remove_and_clear_documents(self):
        store = RAGStore()
        store.add_document("policy.txt", POLICY.encode("utf-8"))
        self.assertTrue(store.remove_document("policy.txt"))
        self.assertFalse(store.remove_document("policy.txt"))
        self.assertEqual(store.search("refund"), [])

        store.add_document("policy.txt", POLICY.encode("utf-8"))
        store.clear()
        self.assertEqual(store.documents, {})
        self.assertEqual(store.chunks, [])

    def test_replacing_a_document_does_not_duplicate_chunks(self):
        store = RAGStore()
        store.add_document("policy.txt", POLICY.encode("utf-8"))
        first = len(store.chunks)
        store.add_document("policy.txt", POLICY.encode("utf-8"))
        self.assertEqual(len(store.chunks), first)
        self.assertEqual(len(store.documents), 1)

    def test_store_round_trip_keeps_retrieval_working(self):
        store = RAGStore()
        store.add_document("policy.txt", POLICY.encode("utf-8"))
        restored = RAGStore.from_dict(store.to_dict())
        self.assertEqual(restored.documents, store.documents)
        self.assertEqual(len(restored.chunks), len(store.chunks))
        self.assertTrue(restored.search("warranty"))

    def test_document_without_enough_text_is_rejected(self):
        store = RAGStore()
        with self.assertRaises(RAGError):
            store.add_document("empty.txt", b"   ")

    def test_missing_optional_pdf_dependency_has_a_clear_error(self):
        if importlib.util.find_spec("pypdf") is not None:
            self.skipTest("pypdf is installed; the optional-dependency error cannot be exercised")
        with self.assertRaises(RAGError) as context:
            extract_text("report.pdf", b"%PDF-1.4 fake")
        self.assertIn("pypdf", str(context.exception))

    def test_missing_optional_docx_dependency_has_a_clear_error(self):
        if importlib.util.find_spec("docx") is not None:
            self.skipTest("python-docx is installed; the optional-dependency error cannot be exercised")
        with self.assertRaises(RAGError) as context:
            extract_text("report.docx", b"PK fake")
        self.assertIn("python-docx", str(context.exception))


class ProviderAndConfigTests(unittest.TestCase):
    def test_local_embeddings_are_deterministic_and_meaningful(self):
        first = local_embed(["refund policy for customers"])
        second = local_embed(["refund policy for customers"])
        self.assertEqual(first, second)
        related = local_embed(["customer refund policy"])[0]
        unrelated = local_embed(["weather forecast tomorrow"])[0]
        self.assertGreater(cosine(first[0], related), cosine(first[0], unrelated))

    def test_extract_json_handles_markdown_fences(self):
        self.assertEqual(extract_json('{"action": "add_kpi"}'), {"action": "add_kpi"})
        self.assertEqual(
            extract_json('Here you go:\n```json\n{"action": "add_kpi"}\n```'),
            {"action": "add_kpi"},
        )
        self.assertIsNone(extract_json("not json"))

    def test_unavailable_ai_keeps_analytics_working(self):
        config = AIConfig()
        self.assertFalse(config.available)
        status = config.public_status()
        self.assertFalse(status["available"])
        self.assertNotIn("api_key", status)

    def test_api_key_is_required_for_hosted_providers_but_not_ollama(self):
        self.assertFalse(AIConfig(provider="openai").available)
        self.assertTrue(AIConfig(provider="openai", api_key="secret").available)
        self.assertTrue(AIConfig(provider="ollama").available)

    def test_public_status_never_exposes_the_key(self):
        config = AIConfig(provider="openai", api_key="super-secret-key")
        status = config.public_status()
        self.assertTrue(status["available"])
        self.assertNotIn("api_key", status)
        self.assertNotIn("super-secret-key", str(status))

    def test_environment_configuration(self):
        env = {
            "RETAILMIND_AI_PROVIDER": "ollama",
            "RETAILMIND_AI_BASE_URL": "http://localhost:11434/v1/",
            "RETAILMIND_AI_MODEL": "llama3",
            "RETAILMIND_AI_EMBEDDING_MODEL": "nomic-embed-text",
            "RETAILMIND_AI_API_KEY": "not-needed",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            config = get_ai_config()
        self.assertEqual(config.provider, "ollama")
        self.assertEqual(config.base_url, "http://localhost:11434/v1")
        self.assertEqual(config.model, "llama3")
        self.assertEqual(config.embedding_model, "nomic-embed-text")
        self.assertTrue(config.available)


if __name__ == "__main__":
    unittest.main()
