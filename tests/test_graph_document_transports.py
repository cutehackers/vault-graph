from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_graph_module_public_integration import fingerprints, indexed_home
from vault_graph.app.catalog_service import CatalogService
from vault_graph.cli.main import app


def document_backend_home(tmp_path: Path, monkeypatch: MonkeyPatch) -> tuple[Path, Path, dict[str, str]]:
    vault, home = indexed_home(tmp_path, monkeypatch)
    switched = CliRunner().invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert switched.exit_code == 0, switched.output
    CatalogService(graph_home_path=home).graph_path.unlink()
    return vault, home, fingerprints(vault) | {f"home:{key}": value for key, value in fingerprints(home).items()}


def assert_source_and_home_unchanged(vault: Path, home: Path, before: dict[str, str]) -> None:
    after = fingerprints(vault) | {f"home:{key}": value for key, value in fingerprints(home).items()}
    assert after == before


def test_document_backend_mcp_stdio_find_related_in_separate_process(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    vault, home, before = document_backend_home(tmp_path, monkeypatch)
    source_root = Path(__file__).resolve().parents[1] / "src"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from vault_graph.cli.main import app; app()", "serve", "--mcp", "--graph-home", str(home)],
        env={**os.environ, "PYTHONPATH": str(source_root)},
    )

    async def query_related() -> None:
        with anyio.fail_after(30):
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool("find_related", {"target": "Source"})
                    assert not result.isError
                    assert result.structuredContent is not None
                    payload = result.structuredContent["payload"]
                    assert payload["result_count"] > 0
                    assert payload["projection_build_id"]

    anyio.run(query_related)
    assert_source_and_home_unchanged(vault, home, before)


def test_document_backend_http_related_in_separate_process(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    vault, home, before = document_backend_home(tmp_path, monkeypatch)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    source_root = Path(__file__).resolve().parents[1] / "src"
    server = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from vault_graph.cli.main import app; app()",
            "serve",
            "--http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--graph-home",
            str(home),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": str(source_root)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        endpoint = f"http://127.0.0.1:{port}/related"
        request = Request(
            endpoint,
            data=json.dumps({"target": "Source"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        deadline = time.monotonic() + 15
        while True:
            if server.poll() is not None:
                stderr = server.stderr.read() if server.stderr is not None else ""
                raise AssertionError(f"HTTP server exited with {server.returncode}: {stderr}")
            try:
                with urlopen(request, timeout=2) as response:
                    assert response.status == 200
                    payload = json.loads(response.read())
                break
            except URLError as error:
                if time.monotonic() >= deadline:
                    raise AssertionError("HTTP server did not become ready within 15 seconds") from error
                time.sleep(0.1)

        assert payload["result_count"] > 0
        assert payload["projection_build_id"]
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)

    assert_source_and_home_unchanged(vault, home, before)
