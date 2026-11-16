"""Claude CLI and `llama-server` fact extractor adapters.

Spec 2026-11-16 D17, I2, I9, F11, A13. Every test fakes the child process or the HTTP call, so no test runs a
real extraction.
"""

from __future__ import annotations

import ast
import io
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from vault_graph.interface.composition.adapters.claude_fact_extractor import FACTS_SCHEMA, ClaudeFactExtractor
from vault_graph.interface.composition.adapters.fact_extractor import (
    ExtractedFact,
    FactExchange,
    FactExtractor,
    FactExtractorUnavailable,
    FactOutputInvalid,
)
from vault_graph.interface.composition.adapters.llama_fact_extractor import LlamaFactExtractor

EXCHANGES = [
    FactExchange(exchange_id="x0001", date="2023-05-20", text="사용자: 물려받은 보석 감정을 어디서 받나요?"),
    FactExchange(exchange_id="x0002", date="2023-05-21", text="User: I moved to Lisbon last week."),
]

SRC = Path(__file__).resolve().parents[1] / "src" / "vault_graph"


def _answer(*facts: dict[str, Any]) -> str:
    return json.dumps({"facts": list(facts)}, ensure_ascii=False)


class FakeRun:
    """Stands in for `subprocess.run` and records each call."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "", error: Exception | None = None):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append({"args": args, **kwargs})
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(args, self.returncode, stdout=self.stdout, stderr=self.stderr)


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> FakeRun:
    fake = FakeRun(
        stdout=_answer(
            {"text": "사용자는 물려받은 보석 감정을 알아보고 있다.", "date": "2023-05-20", "exchange_id": "x0001"}
        )
    )
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class FakeUrlopen:
    """Stands in for `urllib.request.urlopen` and records each request."""

    def __init__(self, body: bytes = b"", error: Exception | None = None):
        self.body = body
        self.error = error
        self.requests: list[tuple[urllib.request.Request, float | None]] = []

    def __call__(self, request: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        self.requests.append((request, timeout))
        if self.error is not None:
            raise self.error
        return FakeResponse(self.body)


def _chat_body(content: str) -> bytes:
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]}).encode("utf-8")


@pytest.fixture
def fake_urlopen(monkeypatch: pytest.MonkeyPatch) -> FakeUrlopen:
    fake = FakeUrlopen(
        _chat_body(_answer({"text": "The user moved to Lisbon.", "date": "2023-05-14", "exchange_id": "x0002"}))
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


# Claude CLI adapter


def test_claude_runs_the_fixed_command_without_bare(fake_run: FakeRun) -> None:
    extractor = ClaudeFactExtractor(endpoint=None, model="claude-sonnet-5-5")

    extractor.extract(EXCHANGES)

    (call,) = fake_run.calls
    args = call["args"]
    assert args == [
        "claude",
        "-p",
        "--model",
        "claude-sonnet-5-5",
        "--json-schema",
        json.dumps(FACTS_SCHEMA),
        "--no-session-persistence",
        "--tools",
        "",
        "--strict-mcp-config",
    ]
    assert "--bare" not in args
    assert call["timeout"] > 0


def test_claude_default_model_is_sonnet() -> None:
    extractor = ClaudeFactExtractor()

    assert extractor.extractor == "claude"
    assert extractor.model == "claude-sonnet-5-5"
    assert isinstance(extractor, FactExtractor)


def test_claude_child_environment_drops_api_key_and_marks_child(
    fake_run: FakeRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-pass")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    ClaudeFactExtractor(endpoint=None, model="claude-sonnet-5-5").extract(EXCHANGES)

    env = fake_run.calls[0]["env"]
    assert "ANTHROPIC_API_KEY" not in env
    assert env["VAULT_GRAPH_FACTS_CHILD"] == "1"
    assert env["PATH"] == "/usr/bin:/bin"


def test_claude_prompt_goes_to_stdin_and_asks_for_the_session_language(fake_run: FakeRun) -> None:
    ClaudeFactExtractor(endpoint=None, model="claude-sonnet-5-5").extract(EXCHANGES)

    call = fake_run.calls[0]
    prompt = call["input"]
    assert all(EXCHANGES[0].text not in arg for arg in call["args"])
    assert "사용자: 물려받은 보석 감정을 어디서 받나요?" in prompt
    assert "x0001" in prompt and "2023-05-20" in prompt
    assert "x0002" in prompt and "2023-05-21" in prompt
    assert "same language" in prompt
    assert "Do not translate" in prompt
    assert "YYYY-MM-DD" in prompt
    assert "exchange_id" in prompt


def test_claude_returns_facts_in_the_session_language(fake_run: FakeRun) -> None:
    facts = ClaudeFactExtractor(endpoint=None, model="claude-sonnet-5-5").extract(EXCHANGES)

    assert facts == [
        ExtractedFact(text="사용자는 물려받은 보석 감정을 알아보고 있다.", date="2023-05-20", exchange_id="x0001")
    ]


def test_claude_with_no_exchanges_does_not_run(fake_run: FakeRun) -> None:
    assert ClaudeFactExtractor(endpoint=None, model="claude-sonnet-5-5").extract([]) == []
    assert fake_run.calls == []


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError("claude"), subprocess.TimeoutExpired(["claude"], 1), PermissionError("claude")],
)
def test_claude_that_cannot_run_is_unavailable(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(subprocess, "run", FakeRun(error=error))

    with pytest.raises(FactExtractorUnavailable):
        ClaudeFactExtractor(endpoint=None, model="claude-sonnet-5-5").extract(EXCHANGES)


def test_claude_nonzero_exit_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRun(stdout="Claude usage limit reached", returncode=1, stderr="Not logged in")
    monkeypatch.setattr(subprocess, "run", fake)

    with pytest.raises(FactExtractorUnavailable, match="exit 1"):
        ClaudeFactExtractor(endpoint=None, model="claude-sonnet-5-5").extract(EXCHANGES)


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "not json",
        "[]",
        json.dumps({"items": []}),
        json.dumps({"facts": "x"}),
        _answer({"text": "a", "date": "2023-05-20"}),
        _answer({"text": "a", "date": "20-05-2023", "exchange_id": "x0001"}),
        _answer({"text": "a", "date": "2023-02-30", "exchange_id": "x0001"}),
        _answer({"text": "a" * 401, "date": "2023-05-20", "exchange_id": "x0001"}),
        _answer({"text": 3, "date": "2023-05-20", "exchange_id": "x0001"}),
    ],
)
def test_claude_answer_off_schema_is_invalid(monkeypatch: pytest.MonkeyPatch, stdout: str) -> None:
    monkeypatch.setattr(subprocess, "run", FakeRun(stdout=stdout))

    with pytest.raises(FactOutputInvalid):
        ClaudeFactExtractor(endpoint=None, model="claude-sonnet-5-5").extract(EXCHANGES)


def test_facts_with_unknown_exchange_or_empty_text_are_dropped_and_text_is_one_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = _answer(
        {"text": "  The user moved\nto Lisbon.  ", "date": "2023-05-14", "exchange_id": "x0002"},
        {"text": "   ", "date": "2023-05-20", "exchange_id": "x0001"},
        {"text": "Invented.", "date": "2023-05-20", "exchange_id": "x9999"},
    )
    monkeypatch.setattr(subprocess, "run", FakeRun(stdout=stdout))

    facts = ClaudeFactExtractor(endpoint=None, model="claude-sonnet-5-5").extract(EXCHANGES)

    assert facts == [ExtractedFact(text="The user moved to Lisbon.", date="2023-05-14", exchange_id="x0002")]


def test_facts_schema_matches_the_contract_fields() -> None:
    item = FACTS_SCHEMA["properties"]["facts"]["items"]
    assert sorted(item["required"]) == ["date", "exchange_id", "text"]
    assert item["properties"]["text"]["maxLength"] == 400
    assert item["properties"]["text"]["minLength"] == 1
    assert item["additionalProperties"] is False


# llama-server adapter


def test_llama_posts_chat_completion_with_schema_to_the_configured_endpoint(fake_urlopen: FakeUrlopen) -> None:
    extractor = LlamaFactExtractor(endpoint="http://127.0.0.1:9999/", model="/models/qwen.gguf")

    facts = extractor.extract(EXCHANGES)

    assert facts == [ExtractedFact(text="The user moved to Lisbon.", date="2023-05-14", exchange_id="x0002")]
    ((request, timeout),) = fake_urlopen.requests
    assert request.full_url == "http://127.0.0.1:9999/v1/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Authorization") is None
    assert timeout is not None and timeout > 0
    assert isinstance(request.data, bytes)
    body = json.loads(request.data)
    assert body["model"] == "/models/qwen.gguf"
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "session_facts", "strict": True, "schema": FACTS_SCHEMA},
    }
    prompt = body["messages"][-1]["content"]
    assert body["messages"][-1]["role"] == "user"
    assert "사용자: 물려받은 보석 감정을 어디서 받나요?" in prompt
    assert "same language" in prompt


def test_llama_names_itself_and_its_model() -> None:
    extractor = LlamaFactExtractor(endpoint="http://127.0.0.1:8080", model="/models/qwen.gguf")

    assert extractor.extractor == "llama-server"
    assert extractor.model == "/models/qwen.gguf"
    assert isinstance(extractor, FactExtractor)


def test_llama_with_no_exchanges_does_not_call(fake_urlopen: FakeUrlopen) -> None:
    assert LlamaFactExtractor(endpoint="http://127.0.0.1:8080", model="m").extract([]) == []
    assert fake_urlopen.requests == []


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError(ConnectionRefusedError(61, "Connection refused")),
        urllib.error.HTTPError("http://127.0.0.1:8080/v1/chat/completions", 503, "Loading model", {}, None),  # type: ignore[arg-type]
        TimeoutError("timed out"),
        ConnectionResetError(54, "reset"),
    ],
)
def test_llama_that_does_not_answer_is_unavailable(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(error=error))

    with pytest.raises(FactExtractorUnavailable):
        LlamaFactExtractor(endpoint="http://127.0.0.1:8080", model="m").extract(EXCHANGES)


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        json.dumps({"choices": []}).encode(),
        json.dumps({"choices": [{"message": {"content": None}}]}).encode(),
        _chat_body("not json"),
        _chat_body(_answer({"text": "a", "date": "2023-05-20"})),
    ],
)
def test_llama_answer_off_schema_is_invalid(monkeypatch: pytest.MonkeyPatch, body: bytes) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(body))

    with pytest.raises(FactOutputInvalid):
        LlamaFactExtractor(endpoint="http://127.0.0.1:8080", model="m").extract(EXCHANGES)


# I2: search, indexing and recall do not import the adapters


def _imported_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_no_module_imports_the_adapters_except_the_llama_adapter() -> None:
    adapters = {
        "vault_graph.interface.composition.adapters.claude_fact_extractor",
        "vault_graph.interface.composition.adapters.llama_fact_extractor",
    }
    allowed = {SRC / "interface/composition/adapters/llama_fact_extractor.py"}
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if path not in allowed and _imported_modules(path) & adapters
    ]
    assert offenders == []
    selection = (SRC / "interface/composition/adapters/fact_extractor_selection.py").read_text(encoding="utf-8")
    assert "importlib.import_module" in selection
