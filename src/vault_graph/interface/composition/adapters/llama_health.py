"""Whether the local `llama-server` answers (spec 2026-11-25-facts-extractor-auto D5, I4).

`llama_server_answers` sends `GET <endpoint>/health` and is true only for HTTP 200. llama-server answers 503 while it
loads the model, so that counts as not answering, like a refused connection or a timeout. Requests go straight to
the endpoint, never through a proxy from the environment.

This module imports no extractor module, so the session-start hook and `vg facts status` can use it (I4).
`tests/conftest.py` replaces `_check` with a fake, so no test reaches a real server through `llama_server_answers`.
"""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request

WORKER_HEALTH_TIMEOUT_SECONDS = 2.0
"""The fact worker checks once per `auto` job."""
STATUS_HEALTH_TIMEOUT_SECONDS = 1.0
"""`vg facts status`."""
HOOK_HEALTH_TIMEOUT_SECONDS = 0.3
"""The session-start hook must not slow the session start."""

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def llama_server_answers(endpoint: str, *, timeout_seconds: float) -> bool:
    """True when `GET <endpoint>/health` returns HTTP 200 within `timeout_seconds`."""
    return _check(endpoint, timeout_seconds)


def check_llama_health(endpoint: str, timeout_seconds: float) -> bool:
    """The real check behind `llama_server_answers`."""
    url = endpoint.rstrip("/") + "/health"
    try:
        with _OPENER.open(url, timeout=timeout_seconds) as response:
            return bool(response.status == 200)
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return False


_check = check_llama_health
