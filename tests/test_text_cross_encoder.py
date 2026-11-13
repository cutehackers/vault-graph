"""fastembed `TextCrossEncoder` adapter (spec 2026-11-13 cross-encoder-rerank D14, F6, F8, A6, A9).

Every test injects fakes for the snapshot lookup, the encoder, and the tokenizer, so no model is downloaded
or loaded.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import types
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from vault_graph.interface.composition.adapters import text_cross_encoder as adapter
from vault_graph.interface.composition.adapters.rerank_presets import (
    RERANK_PRESETS,
    RerankModelUnavailableError,
    RerankPreset,
)
from vault_graph.interface.composition.adapters.text_cross_encoder import (
    MAX_PAIR_TOKENS,
    MAX_QUERY_TOKENS,
    PAIR_SPECIAL_TOKENS,
    TextCrossEncoderReranker,
)
from vault_graph.retrieval.search.reranker import Reranker, RerankError

PRESET = RERANK_PRESETS["mmarco"]
SRC = Path(__file__).resolve().parents[1] / "src"


class FakeEncoding:
    def __init__(self, offsets: list[tuple[int, int]]) -> None:
        self.offsets = offsets


class WordTokenizer:
    """One token per whitespace-separated word, with character offsets like `tokenizers.Encoding`."""

    def __init__(self) -> None:
        self.fail = False

    def encode(self, text: str, add_special_tokens: bool = True) -> FakeEncoding:
        assert add_special_tokens is False
        if self.fail:
            raise RuntimeError("tokenizer broke")
        return FakeEncoding([match.span() for match in re.finditer(r"\S+", text)])


def tokens(text: str) -> int:
    return len(text.split())


class FakeEncoder:
    def __init__(self, scores: Sequence[float] | None = None) -> None:
        self.scores = scores
        self.calls: list[tuple[str, list[str]]] = []
        self.fail = False

    def rerank(self, query: str, documents: Iterable[str]) -> Iterable[float]:
        documents = list(documents)
        self.calls.append((query, documents))
        if self.fail:
            raise RuntimeError("onnx session broke")
        if self.scores is not None:
            return list(self.scores)
        return [float(tokens(document)) for document in documents]


class Fixture:
    def __init__(self, tmp_path: Path) -> None:
        self.snapshot = tmp_path / "snapshot"
        self.encoder = FakeEncoder()
        self.tokenizer = WordTokenizer()
        self.resolver_calls: list[tuple[RerankPreset, Path]] = []
        self.factory_calls: list[tuple[RerankPreset, Path]] = []
        self.tokenizer_calls: list[Path] = []
        self.missing = False
        self.factory_error: Exception | None = None
        self.tokenizer_error: Exception | None = None

    def resolve(self, preset: RerankPreset, models_dir: Path) -> Path:
        self.resolver_calls.append((preset, models_dir))
        if self.missing:
            raise RerankModelUnavailableError("reranker model 'mmarco' unavailable: not in cache")
        return self.snapshot

    def make_encoder(self, preset: RerankPreset, snapshot: Path) -> FakeEncoder:
        self.factory_calls.append((preset, snapshot))
        if self.factory_error is not None:
            raise self.factory_error
        return self.encoder

    def load_tokenizer(self, snapshot: Path) -> WordTokenizer:
        self.tokenizer_calls.append(snapshot)
        if self.tokenizer_error is not None:
            raise self.tokenizer_error
        return self.tokenizer

    def reranker(self, models_dir: Path) -> TextCrossEncoderReranker:
        return TextCrossEncoderReranker(
            PRESET,
            models_dir,
            snapshot_resolver=self.resolve,
            encoder_factory=self.make_encoder,
            tokenizer_loader=self.load_tokenizer,
        )


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path)


def words(prefix: str, count: int) -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


# D14
def test_adapter_is_a_reranker_named_by_its_preset(fx: Fixture, tmp_path: Path) -> None:
    reranker: Reranker = fx.reranker(tmp_path)

    assert reranker.preset == "mmarco"


def test_nothing_loads_until_the_first_rerank_and_then_only_once(fx: Fixture, tmp_path: Path) -> None:
    reranker = fx.reranker(tmp_path / "models")

    assert fx.resolver_calls == []
    assert fx.factory_calls == []
    assert fx.tokenizer_calls == []

    reranker.rerank("q", ["a", "b"])
    reranker.rerank("q", ["a", "b"])

    assert fx.resolver_calls == [(PRESET, tmp_path / "models")]
    assert fx.factory_calls == [(PRESET, fx.snapshot)]
    assert fx.tokenizer_calls == [fx.snapshot]


def test_rerank_returns_indices_by_descending_score(fx: Fixture, tmp_path: Path) -> None:
    fx.encoder.scores = [-2.0, 5.5, 0.1, 5.5]

    assert fx.reranker(tmp_path).rerank("q", ["a", "b", "c", "d"]) == [1, 3, 2, 0]
    assert fx.encoder.calls == [("q", ["a", "b", "c", "d"])]


def test_no_passages_asks_nothing(fx: Fixture, tmp_path: Path) -> None:
    assert fx.reranker(tmp_path).rerank("q", []) == []
    assert fx.resolver_calls == []


# I2: a missing model is reported as unavailable, not swapped for another model.
def test_missing_model_raises_unavailable_and_builds_no_encoder(fx: Fixture, tmp_path: Path) -> None:
    fx.missing = True
    reranker = fx.reranker(tmp_path)

    with pytest.raises(RerankModelUnavailableError, match="mmarco"):
        reranker.rerank("q", ["a", "b"])
    with pytest.raises(RerankModelUnavailableError):
        reranker.rerank("q", ["a", "b"])

    assert len(fx.resolver_calls) == 1
    assert fx.factory_calls == []


def test_default_resolver_only_looks_up_local_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_resolve(preset: RerankPreset, models_dir: Path, *, local_files_only: bool) -> Path:
        calls.append({"preset": preset, "models_dir": models_dir, "local_files_only": local_files_only})
        return tmp_path

    monkeypatch.setattr(adapter, "resolve_rerank_snapshot", fake_resolve)
    reranker = TextCrossEncoderReranker(
        PRESET,
        tmp_path,
        encoder_factory=lambda preset, snapshot: FakeEncoder(),
        tokenizer_loader=lambda snapshot: WordTokenizer(),
    )

    reranker.rerank("q", ["a", "b"])

    assert calls == [{"preset": PRESET, "models_dir": tmp_path, "local_files_only": True}]


# F6, A6
def _pair_fits(query: str, text: str) -> bool:
    return tokens(query) + tokens(text) + PAIR_SPECIAL_TOKENS <= MAX_PAIR_TOKENS


def test_limits_are_256_and_128() -> None:
    assert (MAX_PAIR_TOKENS, MAX_QUERY_TOKENS, PAIR_SPECIAL_TOKENS) == (256, 128, 4)


def test_short_pair_is_passed_unchanged(fx: Fixture, tmp_path: Path) -> None:
    query, text = "what is  rrf?", "reciprocal rank   fusion\nmixes orders"

    fx.reranker(tmp_path).rerank(query, [text, "x"])

    assert fx.encoder.calls == [(query, [text, "x"])]


def test_long_text_is_cut_first_and_the_query_is_kept(fx: Fixture, tmp_path: Path) -> None:
    query = words("q", 40)
    text = words("t", 400)

    fx.reranker(tmp_path).rerank(query, [text, "short"])

    [(sent_query, [sent_text, sent_short])] = fx.encoder.calls
    assert sent_query == query
    assert sent_text == words("t", MAX_PAIR_TOKENS - PAIR_SPECIAL_TOKENS - 40)
    assert _pair_fits(sent_query, sent_text)
    assert sent_short == "short"


def test_query_that_fills_the_budget_is_kept_whole(fx: Fixture, tmp_path: Path) -> None:
    query = words("q", 200)

    fx.reranker(tmp_path).rerank(query, [words("t", 100), "x"])

    [(sent_query, [sent_text, _])] = fx.encoder.calls
    assert sent_query == query
    assert tokens(sent_text) == 52
    assert _pair_fits(sent_query, sent_text)


def test_long_query_is_cut_to_128_tokens(fx: Fixture, tmp_path: Path) -> None:
    query = words("q", 300)

    fx.reranker(tmp_path).rerank(query, ["short text", "x"])

    [(sent_query, [sent_text, _])] = fx.encoder.calls
    assert sent_query == words("q", MAX_QUERY_TOKENS)
    assert sent_text == "short text"


def test_long_query_and_long_text_both_fit(fx: Fixture, tmp_path: Path) -> None:
    query = words("q", 300)
    text = words("t", 300)

    fx.reranker(tmp_path).rerank(query, [text, "x"])

    [(sent_query, [sent_text, _])] = fx.encoder.calls
    assert tokens(sent_query) == MAX_QUERY_TOKENS
    assert sent_text == words("t", MAX_PAIR_TOKENS - PAIR_SPECIAL_TOKENS - MAX_QUERY_TOKENS)
    assert _pair_fits(sent_query, sent_text)


def test_cut_keeps_the_original_characters_of_the_kept_tokens(fx: Fixture, tmp_path: Path) -> None:
    text = "a  b\n" + words("t", 300)

    fx.reranker(tmp_path).rerank(words("q", 10), [text, "x"])

    [(_, [sent_text, _])] = fx.encoder.calls
    assert sent_text.startswith("a  b\nt0 ")
    assert text.startswith(sent_text)


# Errors become RerankError
def test_inference_error_becomes_rerank_error(fx: Fixture, tmp_path: Path) -> None:
    fx.encoder.fail = True

    with pytest.raises(RerankError, match="onnx session broke"):
        fx.reranker(tmp_path).rerank("q", ["a", "b"])


def test_tokenizer_error_becomes_rerank_error(fx: Fixture, tmp_path: Path) -> None:
    fx.tokenizer.fail = True

    with pytest.raises(RerankError, match="tokenizer broke"):
        fx.reranker(tmp_path).rerank("q", ["a", "b"])


def test_score_count_mismatch_becomes_rerank_error(fx: Fixture, tmp_path: Path) -> None:
    fx.encoder.scores = [1.0]

    with pytest.raises(RerankError, match="1 scores for 2 passages"):
        fx.reranker(tmp_path).rerank("q", ["a", "b"])


@pytest.mark.parametrize("failing", ["encoder", "tokenizer"])
def test_load_error_becomes_rerank_error_and_the_next_rerank_tries_again(
    fx: Fixture, tmp_path: Path, failing: str
) -> None:
    error = RuntimeError("bad onnx file")
    if failing == "encoder":
        fx.factory_error = error
    else:
        fx.tokenizer_error = error
    reranker = fx.reranker(tmp_path)

    with pytest.raises(RerankError, match="bad onnx file"):
        reranker.rerank("q", ["a", "b"])

    fx.factory_error = None
    fx.tokenizer_error = None
    assert reranker.rerank("q", ["a", "bb cc"]) == [1, 0]


# F8, A9: fastembed registration happens once per process.
class FakeModelSource:
    def __init__(self, hf: str) -> None:
        self.hf = hf


class FakeTextCrossEncoder:
    registrations: list[dict[str, Any]] = []
    instances: list[dict[str, Any]] = []

    @classmethod
    def add_custom_model(cls, **kwargs: Any) -> None:
        if any(call["model"] == kwargs["model"] for call in cls.registrations):
            raise ValueError("already registered")
        cls.registrations.append(kwargs)

    def __init__(self, **kwargs: Any) -> None:
        type(self).instances.append(kwargs)

    def rerank(self, query: str, documents: Iterable[str]) -> Iterable[float]:
        return [0.0 for _ in documents]


@pytest.fixture
def fake_fastembed(monkeypatch: pytest.MonkeyPatch) -> type[FakeTextCrossEncoder]:
    FakeTextCrossEncoder.registrations = []
    FakeTextCrossEncoder.instances = []
    cross_encoder = types.ModuleType("fastembed.rerank.cross_encoder")
    cast(Any, cross_encoder).TextCrossEncoder = FakeTextCrossEncoder
    model_description = types.ModuleType("fastembed.common.model_description")
    cast(Any, model_description).ModelSource = FakeModelSource
    for name in ("fastembed", "fastembed.rerank", "fastembed.common"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", cross_encoder)
    monkeypatch.setitem(sys.modules, "fastembed.common.model_description", model_description)
    monkeypatch.setattr(adapter, "_REGISTERED_MODELS", set())
    return FakeTextCrossEncoder


def test_default_encoder_registers_the_pinned_file_and_uses_the_snapshot(
    fake_fastembed: type[FakeTextCrossEncoder], tmp_path: Path
) -> None:
    snapshot = tmp_path / "snapshots" / PRESET.revision

    adapter.default_encoder_factory(PRESET, snapshot)

    [registration] = fake_fastembed.registrations
    assert registration["model"] == PRESET.model_name
    assert registration["sources"].hf == PRESET.repo_id
    assert registration["model_file"] == "onnx/model_qint8_arm64.onnx"
    assert registration["license"] == "apache-2.0"
    [instance] = fake_fastembed.instances
    assert instance["model_name"] == PRESET.model_name
    assert instance["specific_model_path"] == str(snapshot)
    assert instance["cache_dir"] == str(snapshot)
    assert instance["local_files_only"] is True


def test_many_encoders_register_once(fake_fastembed: type[FakeTextCrossEncoder], tmp_path: Path) -> None:
    for _ in range(3):
        adapter.default_encoder_factory(PRESET, tmp_path)

    assert len(fake_fastembed.registrations) == 1
    assert len(fake_fastembed.instances) == 3


def test_encoders_built_on_many_threads_register_once(
    fake_fastembed: type[FakeTextCrossEncoder], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original = FakeTextCrossEncoder.add_custom_model.__func__  # type: ignore[attr-defined]
    entered = threading.Event()

    def slow_add_custom_model(cls: type[FakeTextCrossEncoder], /, **kwargs: Any) -> None:
        entered.set()
        threading.Event().wait(0.05)
        original(cls, **kwargs)

    monkeypatch.setattr(FakeTextCrossEncoder, "add_custom_model", classmethod(slow_add_custom_model))
    errors: list[BaseException] = []

    def build() -> None:
        try:
            adapter.default_encoder_factory(PRESET, tmp_path)
        except BaseException as exc:  # noqa: BLE001 - collected for the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=build) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert entered.is_set()
    assert errors == []
    assert len(fake_fastembed.registrations) == 1
    assert len(fake_fastembed.instances) == 8


def test_importing_the_adapter_loads_no_model_library() -> None:
    code = (
        "import sys\n"
        "import vault_graph.interface.composition.adapters.text_cross_encoder\n"
        "print(sorted(name for name in ('huggingface_hub', 'fastembed', 'onnxruntime', 'tokenizers')"
        " if name in sys.modules))\n"
    )
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    assert completed.stdout.strip() == "[]"


def test_fastembed_is_imported_only_in_adapters() -> None:
    adapters_dir = SRC / "vault_graph" / "interface" / "composition" / "adapters"
    importing = {
        path
        for path in (SRC / "vault_graph").rglob("*.py")
        if re.search(r"^\s*(from|import)\s+fastembed\b", path.read_text(encoding="utf-8"), re.MULTILINE)
    }

    assert adapters_dir / "text_cross_encoder.py" in importing
    assert all(path.parent == adapters_dir for path in importing)
