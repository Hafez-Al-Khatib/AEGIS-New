# observability.py
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional, Dict, Any

# -------- Logger setup --------
LOG_FILE = "logs/aegis.log"

logger = logging.getLogger("aegis")
logger.setLevel(logging.INFO)

# Make sure we don't double add handlers in reloads
if not logger.handlers:
    handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5  # 5 MB per file
    )
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | user=%(user)s | agent=%(agent)s | "
        "event=%(event)s | latency_ms=%(latency_ms)s | extra=%(extra)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def log_agent_event(
    agent_name: str,
    user_id: Optional[int],
    event: str,
    latency_ms: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    """
    Log a structured event for any agent in the system
    (Ingestor, Sentinel, Chronicler, Strategist, etc.).
    """
    logger.info(
        "",
        extra={
            "user": user_id or "anonymous",
            "agent": agent_name,
            "event": event,
            "latency_ms": round(latency_ms, 2) if latency_ms is not None else "",
            "extra": extra or {},
        },
    )


def log_api_call(
    path: str,
    method: str,
    status_code: int,
    latency_ms: float,
    user_id: Optional[int] = None,
):
    """
    Log each HTTP request with latency and status.
    Useful for system health and debugging.
    """
    logger.info(
        "",
        extra={
            "user": user_id or "anonymous",
            "agent": f"API::{method} {path}",
            "event": f"status={status_code}",
            "latency_ms": round(latency_ms, 2),
            "extra": {},
        },
    )
