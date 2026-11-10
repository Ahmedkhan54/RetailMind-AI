"""AI provider abstractions and deterministic local embeddings.

The application never *depends* on an AI provider.  When no key is configured
all calculations, dashboards, rule-based NLP and extractive RAG continue to
work.  When a provider is configured it is used only for language generation
and optionally embeddings; numeric answers remain pandas-verified.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
import time
from typing import Any, Iterable
from urllib import error as urlerror
from urllib import request as urlrequest

from retailmind.config import AIConfig, get_ai_config


class AIProviderError(RuntimeError):
    """A sanitized provider failure that is safe to show in the UI."""


def _normalise_config(config: AIConfig) -> AIConfig:
    """Point a default ollama configuration at its local OpenAI-compatible API."""
    if config.provider == "ollama" and config.base_url == "https://api.openai.com/v1":
        return AIConfig(
            provider=config.provider,
            api_key=config.api_key,
            base_url="http://localhost:11434/v1",
            model=config.model,
            embedding_model=config.embedding_model,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
    return config


@dataclass
class AIProvider:
    config: AIConfig

    def __post_init__(self) -> None:
        self.config = _normalise_config(self.config)

    @property
    def available(self) -> bool:
        return self.config.available

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            raise AIProviderError("No AI provider is configured.")
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        body = json.dumps(payload).encode("utf-8")
        last_error = "unknown error"
        for attempt in range(self.config.max_retries + 1):
            try:
                request = urlrequest.Request(url, data=body, headers=self._headers(), method="POST")
                with urlrequest.urlopen(request, timeout=self.config.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urlerror.HTTPError as exc:
                status = exc.code
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", errors="replace")[:300]
                except Exception:
                    pass
                last_error = f"HTTP {status}: {detail}".strip()
                if status in (429, 500, 502, 503, 504) and attempt < self.config.max_retries:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                raise AIProviderError(f"AI provider request failed ({status}).") from None
            except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = type(exc).__name__
                if attempt < self.config.max_retries:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                raise AIProviderError(f"AI provider is unreachable ({last_error}).") from None
        raise AIProviderError(f"AI provider request failed ({last_error}).")

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 700,
        json_mode: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = self._post("chat/completions", payload)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise AIProviderError("AI provider returned an unexpected response shape.") from None
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("AI provider returned an empty response.")
        return content.strip()

    def embed(self, texts: Iterable[str]) -> list[list[float]] | None:
        """Return provider embeddings, or ``None`` so the caller can fall back."""
        if not self.available:
            return None
        items = list(texts)
        if not items:
            return []
        try:
            response = self._post(
                "embeddings",
                {"model": self.config.embedding_model, "input": items},
            )
            data = response.get("data")
            if not isinstance(data, list) or len(data) != len(items):
                return None
            vectors = [item.get("embedding") for item in data]
            if any(not isinstance(vector, list) for vector in vectors):
                return None
            return [[float(value) for value in vector] for vector in vectors]
        except (AIProviderError, TypeError, ValueError, KeyError):
            return None

    def json_chat(self, messages: list[dict[str, str]], *, max_tokens: int = 700) -> dict[str, Any] | None:
        try:
            raw = self.chat(messages, temperature=0.0, max_tokens=max_tokens, json_mode=True)
        except AIProviderError:
            return None
        return extract_json(raw)


def get_provider() -> AIProvider:
    return AIProvider(get_ai_config())


def extract_json(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from a model response, defensively."""
    if not text:
        return None
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


# ---- deterministic local embeddings -----------------------------------
EMBED_DIM = 512


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    bigrams = [f"{words[index]} {words[index + 1]}" for index in range(len(words) - 1)]
    return words + bigrams


def local_embed(texts: Iterable[str]) -> list[list[float]]:
    """Hash-based embedding used when no embedding API is configured.

    This is a real deterministic vector representation (feature hashing), not a
    random placeholder.  It supports lexical semantic retrieval without any
    external service.
    """
    vectors: list[list[float]] = []
    for text in texts:
        vector = [0.0] * EMBED_DIM
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % EMBED_DIM
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        vectors.append([value / norm for value in vector] if norm else vector)
    return vectors


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)
