from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, cast

import pytest

from text_embeddings import EmbeddingInput, EmbeddingModelSpec, FastEmbedTextEmbeddings, TextEmbeddingsError

SPEC = EmbeddingModelSpec("example", "revision", 2, "cosine-v1")


def test_default_backend_requires_local_model_path() -> None:
    with pytest.raises(TextEmbeddingsError, match="backend_factory or local model_path is required"):
        FastEmbedTextEmbeddings(model_spec=SPEC)


def test_default_backend_uses_explicit_local_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    fastembed = types.ModuleType("fastembed")

    class TextEmbedding:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)

        def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> tuple[list[float], ...]:
            return ([1.0, 2.0],)

    cast(Any, fastembed).TextEmbedding = TextEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", fastembed)
    provider = FastEmbedTextEmbeddings(model_spec=SPEC, model_path=tmp_path)

    assert provider.embed((EmbeddingInput("a", "text"),))[0].values == (1.0, 2.0)
    assert calls == [{"model_name": "example", "specific_model_path": str(tmp_path), "local_files_only": True}]


def test_import_and_empty_batch_never_load_backend() -> None:
    provider = FastEmbedTextEmbeddings(model_spec=SPEC, backend_factory=lambda: pytest.fail("backend loaded"))
    assert provider.embed(()) == ()


def test_batch_order_and_model_spec_are_preserved() -> None:
    class Backend:
        def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> tuple[list[float], ...]:
            assert documents == ["first", "second"]
            assert (batch_size, parallel) == (3, 0)
            return ([1, 2], [3, 4])

    provider = FastEmbedTextEmbeddings(model_spec=SPEC, batch_size=3, parallelism=0, backend_factory=Backend)
    vectors = provider.embed((EmbeddingInput("a", "first"), EmbeddingInput("b", "second")))
    assert [(vector.input_id, vector.values, vector.model_spec) for vector in vectors] == [
        ("a", (1.0, 2.0), SPEC),
        ("b", (3.0, 4.0), SPEC),
    ]


@pytest.mark.parametrize(
    ("result", "message"),
    [(([1, 2],), "output count"), (([1], [2]), "dimension mismatch")],
)
def test_invalid_backend_output_is_rejected(result: tuple[list[int], ...], message: str) -> None:
    class Backend:
        def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> tuple[list[int], ...]:
            return result

    provider = FastEmbedTextEmbeddings(model_spec=SPEC, backend_factory=Backend)
    with pytest.raises(TextEmbeddingsError, match=message):
        provider.embed((EmbeddingInput("a", "one"), EmbeddingInput("b", "two")))


def test_duplicate_ids_are_rejected_before_backend_load() -> None:
    provider = FastEmbedTextEmbeddings(model_spec=SPEC, backend_factory=lambda: pytest.fail("backend loaded"))
    with pytest.raises(TextEmbeddingsError, match="input_id must be unique"):
        provider.embed((EmbeddingInput("a", "one"), EmbeddingInput("a", "two")))
