"""Best-effort Redis cache; callers always retain a local-cache fallback."""
from __future__ import annotations
import os
import pandas as pd

def get_frame(key: str) -> pd.DataFrame | None:
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis
        value = redis.from_url(url, socket_connect_timeout=0.2, socket_timeout=0.2).get(key)
        return pd.read_json(value, orient="split") if value else None
    except Exception:
        return None

def set_frame(key: str, frame: pd.DataFrame, ttl: int = 60) -> None:
    url = os.getenv("REDIS_URL")
    if not url:
        return
    try:
        import redis
        redis.from_url(url, socket_connect_timeout=0.2, socket_timeout=0.2).setex(key, ttl, frame.to_json(orient="split", date_format="iso"))
    except Exception:
        return
