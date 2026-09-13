"""Best-effort Redis JSON cache used by read-heavy health views."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger("redis_cache")
_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            import redis
            _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True,
                                           socket_connect_timeout=0.4, socket_timeout=0.4)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis client unavailable: %s", exc)
            _client = False
    return _client


def get_json(key: str) -> Any | None:
    client = _get_client()
    if not client:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001
        logger.info("Redis read skipped: %s", exc)
        return None


def set_json(key: str, value: Any, ttl_seconds: int = 60) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        client.setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False, default=str))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.info("Redis write skipped: %s", exc)
        return False


def delete(key: str) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        client.delete(key)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.info("Redis delete skipped: %s", exc)
        return False


def redis_status() -> dict[str, Any]:
    client = _get_client()
    if not client:
        return {"configured": bool(settings.REDIS_URL), "connected": False}
    try:
        client.ping()
        return {"configured": True, "connected": True}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "connected": False, "error": str(exc)[:160]}
