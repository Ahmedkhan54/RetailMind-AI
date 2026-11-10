"""Dashboard persistence, autosave and undo/redo.

Phase 1 uses a safe session-first workflow plus local JSON files under the
user's state directory.  Database-backed, per-user dashboards require the
authentication layer to be wired (documented as a Phase 2 follow-up).  Only
layout definitions are persisted — never the uploaded dataset.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from retailmind.config import state_dir
from retailmind.models import DashboardConfig
from retailmind.utils import slugify


UNDO_KEY = "rm_undo_stack"
REDO_KEY = "rm_redo_stack"
MAX_HISTORY = 40


def _dashboards_dir() -> Path:
    directory = state_dir() / "dashboards"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe_name(config: DashboardConfig) -> str:
    return f"{slugify(config.name)}-{config.id}.json"


def save_dashboard(config: DashboardConfig) -> Path:
    """Persist a dashboard definition as JSON and return the path."""
    config.touch()
    path = _dashboards_dir() / _safe_name(config)
    path.write_text(config.to_json(), encoding="utf-8")
    return path


def autosave(config: DashboardConfig) -> Path:
    config.touch()
    path = _dashboards_dir() / f"autosave-{slugify(config.dataset_id or 'dataset')}.json"
    path.write_text(config.to_json(), encoding="utf-8")
    return path


def load_dashboard(path: str | Path) -> DashboardConfig:
    return DashboardConfig.from_json(Path(path).read_text(encoding="utf-8"))


def list_dashboards() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(_dashboards_dir().glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries.append(
            {
                "path": str(path),
                "name": payload.get("name", path.stem),
                "id": payload.get("id", ""),
                "dataset_name": payload.get("dataset_name", ""),
                "updated_at": payload.get("updated_at", ""),
                "pages": len(payload.get("pages") or []),
            }
        )
    return entries


def delete_dashboard(path: str | Path) -> bool:
    target = Path(path)
    try:
        target.unlink()
        return True
    except OSError:
        return False


# ---- undo / redo -------------------------------------------------------
def _history_key(base: str, namespace: str | None) -> str:
    """Scope history per dataset so undo can never load another dataset."""
    return f"{base}_{namespace}" if namespace else base


def push_undo(state: Any, config: DashboardConfig, namespace: str | None = None) -> None:
    undo_key = _history_key(UNDO_KEY, namespace)
    redo_key = _history_key(REDO_KEY, namespace)
    stack = list(state.get(undo_key) or [])
    snapshot = config.to_json()
    if stack and stack[-1] == snapshot:
        return
    stack.append(snapshot)
    state[undo_key] = stack[-MAX_HISTORY:]
    state[redo_key] = []


def can_undo(state: Any, namespace: str | None = None) -> bool:
    return bool(state.get(_history_key(UNDO_KEY, namespace)))


def can_redo(state: Any, namespace: str | None = None) -> bool:
    return bool(state.get(_history_key(REDO_KEY, namespace)))


def undo(state: Any, current: DashboardConfig, namespace: str | None = None) -> DashboardConfig | None:
    undo_key = _history_key(UNDO_KEY, namespace)
    redo_key = _history_key(REDO_KEY, namespace)
    stack = list(state.get(undo_key) or [])
    if not stack:
        return None
    snapshot = stack.pop()
    redo = list(state.get(redo_key) or [])
    redo.append(current.to_json())
    state[undo_key] = stack
    state[redo_key] = redo[-MAX_HISTORY:]
    return DashboardConfig.from_json(snapshot)


def redo(state: Any, current: DashboardConfig, namespace: str | None = None) -> DashboardConfig | None:
    undo_key = _history_key(UNDO_KEY, namespace)
    redo_key = _history_key(REDO_KEY, namespace)
    redo = list(state.get(redo_key) or [])
    if not redo:
        return None
    snapshot = redo.pop()
    undo_stack = list(state.get(undo_key) or [])
    undo_stack.append(current.to_json())
    state[undo_key] = undo_stack[-MAX_HISTORY:]
    state[redo_key] = redo
    return DashboardConfig.from_json(snapshot)


def clear_history(state: Any, namespace: str | None = None) -> None:
    state[_history_key(UNDO_KEY, namespace)] = []
    state[_history_key(REDO_KEY, namespace)] = []


def snapshot(state: Any, key: str, value: Any) -> None:
    state[key] = value
