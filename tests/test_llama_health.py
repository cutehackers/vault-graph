"""The llama-server health check (spec 2026-11-25-facts-extractor-auto D5, I4, A7, A8)."""

from __future__ import annotations

import http.server
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from tests.conftest import FakeLlamaHealth
from vault_graph.interface.composition.adapters import llama_health
from vault_graph.interface.composition.adapters.llama_health import check_llama_health, llama_server_answers


@contextmanager
def _server(status: int, *, delay: float = 0.0) -> Iterator[str]:
    paths: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server names
            paths.append(self.path)
            time.sleep(delay)
            body = b'{"status":"ok"}' if status == 200 else b'{"error":{"message":"Loading model"}}'
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()
    assert all(path == "/health" for path in paths)


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_http_200_on_health_answers() -> None:
    with _server(200) as endpoint:
        assert check_llama_health(endpoint, 1.0) is True


def test_http_503_while_the_model_loads_does_not_answer() -> None:
    with _server(503) as endpoint:
        assert check_llama_health(endpoint, 1.0) is False


def test_refused_connection_does_not_answer() -> None:
    assert check_llama_health(f"http://127.0.0.1:{_closed_port()}", 1.0) is False


def test_slow_server_does_not_answer_within_the_hook_timeout() -> None:
    with _server(200, delay=2.0) as endpoint:
        started = time.monotonic()
        answered = check_llama_health(endpoint, llama_health.HOOK_HEALTH_TIMEOUT_SECONDS)
        elapsed = time.monotonic() - started

    assert answered is False
    assert elapsed < 1.0


def test_timeouts_per_caller() -> None:
    assert llama_health.WORKER_HEALTH_TIMEOUT_SECONDS == 2.0
    assert llama_health.STATUS_HEALTH_TIMEOUT_SECONDS == 1.0
    assert llama_health.HOOK_HEALTH_TIMEOUT_SECONDS == 0.3


def test_answers_goes_through_the_fake_in_tests(fake_llama_health: FakeLlamaHealth) -> None:
    assert llama_server_answers("http://x", timeout_seconds=0.3) is False
    fake_llama_health.up = True
    assert llama_server_answers("http://x", timeout_seconds=0.3) is True
    assert fake_llama_health.calls == [("http://x", 0.3), ("http://x", 0.3)]


def test_hook_status_and_health_do_not_import_extractor_modules() -> None:
    code = (
        "import sys\n"
        "import vault_graph.interface.cli.hook_commands\n"
        "import vault_graph.interface.cli.facts_commands\n"
        "import vault_graph.interface.composition.adapters.llama_health\n"
        "names = ('claude_fact_extractor', 'llama_fact_extractor', 'fact_extractor', 'fact_worker',\n"
        "         'fact_extractor_selection')\n"
        "loaded = [m for m in sys.modules if m.rsplit('.', 1)[-1] in names]\n"
        "print(loaded)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    assert result.stdout.strip() == "[]"
