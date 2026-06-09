from pathlib import Path

import pytest

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vault_graph.errors import TextEmbeddingsError


def test_empty_input_returns_empty_output() -> None:
    embeddings = DeterministicTextEmbeddings(
        EmbeddingModelSpec(
            model_name="deterministic",
            model_version="test",
            dimensions=4,
            spec_version="embedding-spec-v1",
        )
    )

    assert embeddings.embed(()) == ()


def test_text_embeddings_returns_stable_dimensioned_vectors() -> None:
    spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="test",
        dimensions=4,
        spec_version="embedding-spec-v1",
    )
    embeddings = DeterministicTextEmbeddings(spec)
    inputs = (
        EmbeddingInput(input_id="first", text="alpha"),
        EmbeddingInput(input_id="second", text="beta"),
    )

    first = embeddings.embed(inputs)
    second = embeddings.embed(inputs)

    assert first == second
    assert tuple(vector.input_id for vector in first) == ("first", "second")
    assert all(vector.model_spec == spec for vector in first)
    assert all(len(vector.values) == 4 for vector in first)


def test_input_id_is_only_a_batch_correlation_key() -> None:
    spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="test",
        dimensions=3,
        spec_version="embedding-spec-v1",
    )
    embeddings = DeterministicTextEmbeddings(spec)

    vector = embeddings.embed((EmbeddingInput(input_id="batch-item-1", text="wiki/page.md"),))[0]

    assert vector.input_id == "batch-item-1"
    assert not hasattr(vector, "vault_id")
    assert not hasattr(vector, "document_id")
    assert not hasattr(vector, "chunk_id")
    assert not hasattr(vector, "path")


def test_duplicate_input_id_fails_loudly_within_one_call() -> None:
    spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="test",
        dimensions=4,
        spec_version="embedding-spec-v1",
    )
    embeddings = DeterministicTextEmbeddings(spec)
    inputs = (
        EmbeddingInput(input_id="duplicate", text="alpha"),
        EmbeddingInput(input_id="duplicate", text="beta"),
    )

    with pytest.raises(TextEmbeddingsError, match="input_id must be unique"):
        embeddings.embed(inputs)


def test_embedding_spec_rejects_invalid_dimensions() -> None:
    with pytest.raises(TextEmbeddingsError, match="dimensions must be positive"):
        EmbeddingModelSpec(
            model_name="deterministic",
            model_version="test",
            dimensions=0,
            spec_version="embedding-spec-v1",
        )


def test_embedding_vector_rejects_dimension_mismatch() -> None:
    spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="test",
        dimensions=4,
        spec_version="embedding-spec-v1",
    )

    with pytest.raises(TextEmbeddingsError, match="embedding dimension mismatch"):
        EmbeddingVector(input_id="bad", values=(1.0, 2.0), model_spec=spec)


def test_text_embeddings_does_not_write_files(tmp_path: Path) -> None:
    embeddings = DeterministicTextEmbeddings(
        EmbeddingModelSpec(
            model_name="deterministic",
            model_version="test",
            dimensions=4,
            spec_version="embedding-spec-v1",
        )
    )
    before = tuple(tmp_path.iterdir())

    embeddings.embed((EmbeddingInput(input_id="one", text=str(tmp_path)),))

    assert tuple(tmp_path.iterdir()) == before


def test_text_embeddings_exposes_no_download_availability() -> None:
    spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="test",
        dimensions=4,
        spec_version="embedding-spec-v1",
    )
    embeddings = DeterministicTextEmbeddings(spec)

    assert embeddings.can_embed_without_download() is True
