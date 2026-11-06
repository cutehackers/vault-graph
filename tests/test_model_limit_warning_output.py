"""Spec 2026-11-05 §4.2.6-11: session windows over 512 model tokens are counted with the model tokenizer
and reported in the `vg index` output."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_cli_vector_indexing import _ConfiguredDeterministicTextEmbeddings
from tests.test_vector_indexer import SPEC
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.text_embeddings import (
    EMBEDDING_PRESETS,
    FastEmbedTextEmbeddings,
    FastEmbedTextEmbeddingsConfig,
)

SESSIONS = Path(__file__).parent / "fixtures" / "session_v2" / "raw" / "sessions"


def _word_tokenizer(folder: Path) -> Path:
    """A whitespace tokenizer that truncates at 4 tokens, saved as `tokenizer.json`."""
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace

    tokenizer = Tokenizer(WordLevel({"[UNK]": 0}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    tokenizer.enable_truncation(max_length=4)
    folder.mkdir(parents=True, exist_ok=True)
    tokenizer.save(str(folder / "tokenizer.json"))
    return folder


def _embeddings(snapshot: Path | None) -> FastEmbedTextEmbeddings:
    def resolve(_: FastEmbedTextEmbeddingsConfig) -> Path:
        if snapshot is None:
            raise FileNotFoundError("no snapshot")
        return snapshot

    return FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(preset=EMBEDDING_PRESETS["e5-small"]),
        backend_factory=lambda *_: pytest.fail("counting must not load the model"),
        snapshot_resolver=resolve,
    )


def test_model_tokens_use_the_tokenizer_with_the_document_prefix_and_no_truncation(tmp_path: Path) -> None:
    from tokenizers import Tokenizer

    snapshot = _word_tokenizer(tmp_path / "snapshot")
    embeddings = _embeddings(snapshot)
    prefix = EMBEDDING_PRESETS["e5-small"].document_prefix
    prefix_tokens = len(Tokenizer.from_file(str(snapshot / "tokenizer.json")).encode(prefix).ids)

    # The saved tokenizer truncates at 4; the count must not.
    assert embeddings.count_model_tokens("one two three four five six") == prefix_tokens + 6


def test_model_tokens_fall_back_to_the_byte_estimate_without_a_tokenizer() -> None:
    assert _embeddings(None).count_model_tokens("가나다") == 3


class _LongCounting(_ConfiguredDeterministicTextEmbeddings):
    """Every text counts as 600 model tokens."""

    def count_model_tokens(self, text: str) -> int:
        return 600


def test_vg_index_prints_the_model_limit_warning_for_session_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    shutil.copytree(SESSIONS, vault / "raw" / "sessions")
    home = tmp_path / "home"
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(home)]).exit_code == 0
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", lambda _: _LongCounting(SPEC))

    result = runner.invoke(app, ["index", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    warnings = [line for line in result.stdout.splitlines() if line.startswith("vector_warning: ")]
    assert len(warnings) == 1
    assert "512" in warnings[0]
    assert "the model tokenizer" in warnings[0]
