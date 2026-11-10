"""Application configuration and environment handling for RetailMind AI.

No secret value is ever rendered or logged.  The AI provider is entirely
optional: when it is not configured, every deterministic analytics feature
continues to work and the UI states that AI narrative is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None


APP_NAME = "RetailMind AI"
APP_TITLE = "RetailMind AI – Intelligent Universal Business Analytics Platform"
TAGLINE = "Understand Your Business. Predict Your Future. Grow Smarter."
VERSION = "2.0.0-phase2"

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SUPPORTED_EXTENSIONS = ("csv", "xlsx", "xls", "xlsm")
MAX_PREVIEW_ROWS = 200

AGGREGATIONS = ("sum", "avg", "count", "min", "max")
CHART_TYPES = ("bar", "line", "area", "pie", "donut", "scatter", "histogram", "table", "matrix")
THEME_PRESETS = ("dark", "light", "midnight", "corporate")
PALETTES = {
    "dark": ["#7c5cff", "#22c55e", "#38bdf8", "#f59e0b", "#f472b6", "#a3e635", "#fb7185", "#2dd4bf"],
    "light": ["#4f46e5", "#059669", "#0284c7", "#d97706", "#db2777", "#65a30d", "#e11d48", "#0d9488"],
    "midnight": ["#60a5fa", "#34d399", "#f472b6", "#fbbf24", "#a78bfa", "#22d3ee", "#fb7185", "#84cc16"],
    "corporate": ["#1d4ed8", "#047857", "#b45309", "#7c3aed", "#be123c", "#0f766e", "#4338ca", "#4d7c0f"],
}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if load_dotenv is not None:
    # ``override=False`` keeps real environment variables authoritative.
    load_dotenv(_PROJECT_ROOT / ".env", override=False)


def state_dir() -> Path:
    """Return a writable, user-scoped directory for small JSON state files.

    Dashboards never store the uploaded dataset itself.  The default lives
    outside the project so a read-only checkout still works.
    """
    configured = os.getenv("RETAILMIND_STATE_DIR")
    base = Path(configured).expanduser() if configured else Path.home() / ".retailmind"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Fall back to a temporary directory if the home directory is locked.
        import tempfile

        base = Path(tempfile.gettempdir()) / "retailmind_state"
        base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass(frozen=True)
class AIConfig:
    """Resolved AI configuration.

    ``available`` only becomes true when a provider *and* an API key are set.
    ``ollama`` is treated as keyless and therefore allowed without a key.
    """

    provider: str = "none"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    timeout: float = 30.0
    max_retries: int = 2

    @property
    def available(self) -> bool:
        if self.provider in ("none", ""):
            return False
        if self.provider == "ollama":
            return True
        return bool(self.api_key)

    def public_status(self) -> dict[str, object]:
        """Status safe to show in the UI; never includes the API key."""
        if self.provider in ("none", ""):
            return {
                "available": False,
                "provider": "none",
                "model": None,
                "message": "AI narrative is off. Rule-based analytics and verified calculations are fully available.",
            }
        if not self.available:
            return {
                "available": False,
                "provider": self.provider,
                "model": self.model,
                "message": f"{self.provider} is selected but no API key is configured. Using deterministic fallbacks.",
            }
        return {
            "available": True,
            "provider": self.provider,
            "model": self.model,
            "message": f"Connected to {self.provider} ({self.model}). Calculations remain pandas-verified.",
        }


def get_ai_config() -> AIConfig:
    """Read AI settings from environment variables (never hardcoded)."""
    provider = os.getenv("RETAILMIND_AI_PROVIDER", "none").strip().lower() or "none"
    try:
        timeout = float(os.getenv("RETAILMIND_AI_TIMEOUT", "30"))
    except ValueError:
        timeout = 30.0
    try:
        retries = max(0, int(os.getenv("RETAILMIND_AI_MAX_RETRIES", "2")))
    except ValueError:
        retries = 2
    return AIConfig(
        provider=provider,
        api_key=os.getenv("RETAILMIND_AI_API_KEY", "").strip(),
        base_url=os.getenv("RETAILMIND_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        model=os.getenv("RETAILMIND_AI_MODEL", "gpt-4o-mini").strip(),
        embedding_model=os.getenv("RETAILMIND_AI_EMBEDDING_MODEL", "text-embedding-3-small").strip(),
        timeout=timeout,
        max_retries=retries,
    )
