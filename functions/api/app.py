"""API Lambda — single handler dispatching to route modules.

Uses a tiny URL pattern matcher (no Flask/FastAPI to keep deployment lean and
cold start under 400ms). Routes live in functions/api/routes/*.py and register
themselves via a simple decorator.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


# ----- router -----

ROUTES: list[tuple[re.Pattern, Callable[..., Any]]] = []


def route(pattern: str):
    """Register a handler for a URL pattern. ``{name}`` segments become kwargs."""
    placeholder = re.compile(r"\{(\w+)\}")
    regex_pattern = placeholder.sub(r"(?P<\1>[^/]+)", pattern)
    compiled = re.compile(f"^{regex_pattern}$")

    def decorator(fn):
        ROUTES.append((compiled, fn))
        return fn

    return decorator


# Import routes so they self-register (must happen after `route` is defined).
from routes import (  # noqa: E402,F401
    championship,
    circuit_analysis,
    drivers,
    fingerprints,
    predictions,
    qualifying,
    races,
    standings,
    teams,
    upgrades,
)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """API Gateway proxy entry point."""
    path = event.get("path") or event.get("rawPath") or "/"
    method = (event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method") or "GET").upper()

    if method == "OPTIONS":
        return _response(204, "")

    for pattern, fn in ROUTES:
        match = pattern.match(path)
        if not match:
            continue
        try:
            body = fn(**match.groupdict(), event=event)
            return _response(200, body)
        except KeyError as exc:
            logger.info("not found: %s", exc)
            return _response(404, {"error": "not found", "detail": str(exc)})
        except ValueError as exc:
            return _response(400, {"error": "bad request", "detail": str(exc)})
        except Exception:
            logger.exception("route handler failed: %s", path)
            return _response(500, {"error": "internal error"})

    return _response(404, {"error": "no route", "path": path})


def _response(status: int, body: Any) -> dict[str, Any]:
    if isinstance(body, (dict, list)):
        payload = json.dumps(body, default=str)
        content_type = "application/json"
    else:
        payload = str(body)
        content_type = "text/plain"
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": content_type,
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            # No cache during active dev — predictions get regenerated and
            # 5-min browser/CDN caching makes 'why is my data stale?' a recurring
            # support thread. Drop to 30s once we're stable, or per-route.
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
        "body": payload,
    }
