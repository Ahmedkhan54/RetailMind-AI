"""RetailMind AI intelligence layer: provider, NLP, chat, assistant, insights, RAG."""

from __future__ import annotations

from retailmind.ai.provider import (
    AIProvider,
    AIProviderError,
    cosine,
    extract_json,
    get_provider,
    local_embed,
)

__all__ = [
    "AIProvider",
    "AIProviderError",
    "cosine",
    "extract_json",
    "get_provider",
    "local_embed",
]
