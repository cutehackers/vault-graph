from pathlib import Path

import pytest

from vault_graph.embeddings.fastembed_text_embeddings import (
    DEFAULT_FASTEMBED_MODEL_SPEC,
    FASTEMBED_ARTIFACT_REPO_ID,
    SOURCE_MODEL_REVISION,
    FastEmbedTextEmbeddings,
    FastEmbedTextEmbeddingsConfig,
)
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingVector
from vault_graph.errors import TextEmbeddingsError


def test_default_model_spec_is_fixed() -> None:
    assert DEFAULT_FASTEMBED_MODEL_SPEC.model_name == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert DEFAULT_FASTEMBED_MODEL_SPEC.model_version == "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
    assert DEFAULT_FASTEMBED_MODEL_SPEC.dimensions == 384
    assert DEFAULT_FASTEMBED_MODEL_SPEC.spec_version == "fastembed-multilingual-minilm-l12-v2-cosine-v1"


def test_fastembed_artifact_source_is_pinned() -> None:
    config = FastEmbedTextEmbeddingsConfig()

    assert config.artifact_repo_id == FASTEMBED_ARTIFACT_REPO_ID
    assert config.model_version == "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
    assert config.source_model_revision == SOURCE_MODEL_REVISION


def test_runtime_config_does_not_change_model_spec(tmp_path: Path) -> None:
    first = FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache", embedding_batch_size=16)
    second = FastEmbedTextEmbeddingsConfig(
        cache_dir=tmp_path / "cache",
        embedding_batch_size=512,
        embedding_parallelism=0,
    )

    assert first.model_spec() == second.model_spec()


def test_duplicate_input_ids_fail_before_backend_load(tmp_path: Path) -> None:
    embeddings = FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache"),
        backend_factory=lambda _, __: pytest.fail("backend must not load"),
    )

    with pytest.raises(TextEmbeddingsError, match="input_id must be unique"):
        embeddings.embed(
            (
                EmbeddingInput(input_id="same", text="alpha"),
                EmbeddingInput(input_id="same", text="beta"),
            )
        )


def test_embed_binds_backend_vectors_to_input_ids(tmp_path: Path) -> None:
    class Backend:
        def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> tuple[list[float], ...]:
            assert documents == ["alpha", "beta"]
            assert batch_size == 256
            assert parallel is None
            return ([0.1] * 384, [0.2] * 384)

    embeddings = FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache"),
        backend_factory=lambda _, __: Backend(),
        snapshot_resolver=lambda _: tmp_path / "cache" / "snapshot",
    )

    vectors = embeddings.embed((EmbeddingInput(input_id="a", text="alpha"), EmbeddingInput(input_id="b", text="beta")))

    assert vectors == (
        EmbeddingVector(input_id="a", values=tuple([0.1] * 384), model_spec=DEFAULT_FASTEMBED_MODEL_SPEC),
        EmbeddingVector(input_id="b", values=tuple([0.2] * 384), model_spec=DEFAULT_FASTEMBED_MODEL_SPEC),
    )


def test_backend_dimension_mismatch_fails_loudly(tmp_path: Path) -> None:
    class Backend:
        def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> tuple[list[float], ...]:
            return ([0.1] * 2,)

    embeddings = FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache"),
        backend_factory=lambda _, __: Backend(),
        snapshot_resolver=lambda _: tmp_path / "cache" / "snapshot",
    )

    with pytest.raises(TextEmbeddingsError, match="embedding dimension mismatch"):
        embeddings.embed((EmbeddingInput(input_id="a", text="alpha"),))


def test_model_unavailable_error_is_clear(tmp_path: Path) -> None:
    def fail_snapshot(_: FastEmbedTextEmbeddingsConfig) -> Path:
        raise TextEmbeddingsError("embedding model unavailable: offline and not cached")

    embeddings = FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path / "cache"),
        backend_factory=lambda _, __: pytest.fail("backend must not load"),
        snapshot_resolver=fail_snapshot,
    )

    with pytest.raises(TextEmbeddingsError, match="embedding model unavailable"):
        embeddings.embed((EmbeddingInput(input_id="a", text="alpha"),))


def test_fastembed_can_check_local_artifact_without_loading_backend(tmp_path: Path) -> None:
    calls: list[str] = []

    def resolver(_: FastEmbedTextEmbeddingsConfig) -> Path:
        calls.append("resolver")
        return tmp_path / "snapshot"

    embeddings = FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=tmp_path, local_files_only=True),
        snapshot_resolver=resolver,
        backend_factory=lambda _config, _path: pytest.fail("backend must not load"),
    )

    assert embeddings.can_embed_without_download() is True
    assert calls == ["resolver"]
