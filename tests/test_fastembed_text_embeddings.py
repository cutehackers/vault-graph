import re
import sys
import types
import warnings
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import pytest

from vault_graph.errors import TextEmbeddingsError
from vault_graph.interface.composition.adapters import text_embeddings as adapter
from vault_graph.interface.composition.adapters.text_embeddings import (
    DEFAULT_EMBEDDING_PRESET,
    EMBEDDING_PRESETS,
    EmbeddingPreset,
    FastEmbedTextEmbeddings,
    FastEmbedTextEmbeddingsConfig,
    _default_backend_factory,
    _resolve_snapshot,
    text_embeddings_for,
)
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.embedding_selection import EmbeddingSelection, save_embedding_selection
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput, EmbeddingVector

MINILM = EMBEDDING_PRESETS["minilm"]
ARCTIC = EMBEDDING_PRESETS["arctic-l"]
E5 = EMBEDDING_PRESETS["e5-small"]


def _config(preset: EmbeddingPreset, tmp_path: Path, **kwargs: Any) -> FastEmbedTextEmbeddingsConfig:
    return FastEmbedTextEmbeddingsConfig(preset=preset, cache_dir=tmp_path / "cache", **kwargs)


# Preset table (A-4, A-5) ----------------------------------------------------------------------


def test_preset_table_has_three_presets_and_e5_small_is_the_default() -> None:
    assert set(EMBEDDING_PRESETS) == {"arctic-l", "e5-small", "minilm"}
    assert DEFAULT_EMBEDDING_PRESET == "e5-small"
    assert all(name == preset.name for name, preset in EMBEDDING_PRESETS.items())


def test_every_preset_pins_a_full_commit_revision_and_a_distinct_spec_version() -> None:
    for preset in EMBEDDING_PRESETS.values():
        assert re.fullmatch(r"[0-9a-f]{40}", preset.revision), preset.name
    spec_versions = [preset.spec_version for preset in EMBEDDING_PRESETS.values()]
    assert len(set(spec_versions)) == len(spec_versions)


def test_minilm_preset_keeps_the_previous_model_spec() -> None:
    spec = MINILM.model_spec()

    assert spec.model_name == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert spec.model_version == "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
    assert spec.dimensions == 384
    assert spec.spec_version == "fastembed-multilingual-minilm-l12-v2-cosine-v1"
    assert MINILM.repo_id == "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
    assert MINILM.fastembed_registration == "builtin"
    assert MINILM.files is None
    assert (MINILM.query_prefix, MINILM.document_prefix) == ("", "")


def test_arctic_l_and_e5_small_are_custom_int8_presets_with_limited_files() -> None:
    assert ARCTIC.model_name == "Snowflake/snowflake-arctic-embed-l-v2.0"
    assert ARCTIC.repo_id == "Snowflake/snowflake-arctic-embed-l-v2.0"
    assert ARCTIC.dimensions == 1024
    assert (ARCTIC.pooling, ARCTIC.normalization) == ("CLS", True)
    assert (ARCTIC.query_prefix, ARCTIC.document_prefix) == ("query: ", "")
    assert E5.model_name == "Xenova/multilingual-e5-small"
    assert E5.repo_id == "Xenova/multilingual-e5-small"
    assert E5.dimensions == 384
    assert (E5.pooling, E5.normalization) == ("MEAN", True)
    assert (E5.query_prefix, E5.document_prefix) == ("query: ", "passage: ")
    for preset in (ARCTIC, E5):
        assert preset.fastembed_registration == "custom"
        assert preset.model_file == "onnx/model_int8.onnx"
        assert preset.files is not None
        assert preset.model_file in preset.files
        for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"):
            assert name in preset.files


def test_old_single_model_constants_are_gone() -> None:
    for name in ("DEFAULT_FASTEMBED_MODEL_SPEC", "FASTEMBED_ARTIFACT_REPO_ID", "SOURCE_MODEL_REVISION"):
        assert not hasattr(adapter, name)


# Config ---------------------------------------------------------------------------------------


def test_runtime_config_does_not_change_model_spec(tmp_path: Path) -> None:
    first = _config(ARCTIC, tmp_path, embedding_batch_size=16)
    second = _config(ARCTIC, tmp_path, embedding_batch_size=512, embedding_parallelism=0)

    assert first.model_spec() == second.model_spec() == ARCTIC.model_spec()


def test_local_files_only_check_keeps_every_other_config_field(tmp_path: Path) -> None:
    seen: list[FastEmbedTextEmbeddingsConfig] = []
    config = _config(E5, tmp_path, embedding_batch_size=8, embedding_parallelism=2)

    def resolver(given: FastEmbedTextEmbeddingsConfig) -> Path:
        seen.append(given)
        return tmp_path / "snapshot"

    embeddings = FastEmbedTextEmbeddings(
        config=config,
        snapshot_resolver=resolver,
        backend_factory=lambda _config, _path: pytest.fail("backend must not load"),
    )

    assert embeddings.can_embed_without_download() is True
    assert seen == [FastEmbedTextEmbeddingsConfig(**{**vars(config), "local_files_only": True})]


# Embedding ------------------------------------------------------------------------------------


def test_duplicate_input_ids_fail_before_backend_load(tmp_path: Path) -> None:
    embeddings = FastEmbedTextEmbeddings(
        config=_config(MINILM, tmp_path),
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
        config=_config(MINILM, tmp_path),
        backend_factory=lambda _, __: Backend(),
        snapshot_resolver=lambda _: tmp_path / "cache" / "snapshot",
    )

    vectors = embeddings.embed((EmbeddingInput(input_id="a", text="alpha"), EmbeddingInput(input_id="b", text="beta")))

    assert vectors == (
        EmbeddingVector(input_id="a", values=tuple([0.1] * 384), model_spec=MINILM.model_spec()),
        EmbeddingVector(input_id="b", values=tuple([0.2] * 384), model_spec=MINILM.model_spec()),
    )


class _RecordingBackend:
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions
        self.documents: list[str] = []

    def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> tuple[list[float], ...]:
        self.documents.extend(documents)
        return tuple([0.5] * self.dimensions for _ in documents)


@pytest.mark.parametrize(
    ("name", "query_text", "document_text"),
    [("e5-small", "query: x", "passage: y"), ("arctic-l", "query: x", "y"), ("minilm", "x", "y")],
)
def test_query_and_document_prefixes_follow_the_preset(
    tmp_path: Path, name: str, query_text: str, document_text: str
) -> None:
    preset = EMBEDDING_PRESETS[name]
    backend = _RecordingBackend(preset.dimensions)
    embeddings = FastEmbedTextEmbeddings(
        config=_config(preset, tmp_path),
        backend_factory=lambda _, __: backend,
        snapshot_resolver=lambda _: tmp_path / "snapshot",
    )

    query = embeddings.embed_query("x")
    documents = embeddings.embed((EmbeddingInput(input_id="doc", text="y"),))

    assert backend.documents == [query_text, document_text]
    assert query.model_spec == preset.model_spec()
    assert len(query.values) == preset.dimensions
    assert documents[0].input_id == "doc"


def test_backend_dimension_mismatch_fails_loudly(tmp_path: Path) -> None:
    class Backend:
        def embed(self, documents: list[str], *, batch_size: int, parallel: int | None) -> tuple[list[float], ...]:
            return ([0.1] * 2,)

    embeddings = FastEmbedTextEmbeddings(
        config=_config(MINILM, tmp_path),
        backend_factory=lambda _, __: Backend(),
        snapshot_resolver=lambda _: tmp_path / "cache" / "snapshot",
    )

    with pytest.raises(TextEmbeddingsError, match="embedding dimension mismatch"):
        embeddings.embed((EmbeddingInput(input_id="a", text="alpha"),))


def test_model_unavailable_error_is_clear(tmp_path: Path) -> None:
    def fail_snapshot(_: FastEmbedTextEmbeddingsConfig) -> Path:
        raise TextEmbeddingsError("embedding model unavailable: offline and not cached")

    embeddings = FastEmbedTextEmbeddings(
        config=_config(MINILM, tmp_path),
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
        config=FastEmbedTextEmbeddingsConfig(preset=MINILM, cache_dir=tmp_path, local_files_only=True),
        snapshot_resolver=resolver,
        backend_factory=lambda _config, _path: pytest.fail("backend must not load"),
    )

    assert embeddings.can_embed_without_download() is True
    assert calls == ["resolver"]


# Download -------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(EMBEDDING_PRESETS))
def test_snapshot_download_uses_the_preset_repo_revision_and_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    calls: list[dict[str, object]] = []
    module = types.ModuleType("huggingface_hub")

    def snapshot_download(**kwargs: object) -> str:
        calls.append(kwargs)
        return str(tmp_path / "snapshot")

    cast(Any, module).snapshot_download = snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    preset = EMBEDDING_PRESETS[name]

    assert _resolve_snapshot(_config(preset, tmp_path, local_files_only=True)) == tmp_path / "snapshot"

    assert calls == [
        {
            "repo_id": preset.repo_id,
            "revision": preset.revision,
            "cache_dir": str(tmp_path / "cache"),
            "local_files_only": True,
            "allow_patterns": list(preset.files) if preset.files is not None else None,
        }
    ]


# Backend --------------------------------------------------------------------------------------


class _PoolingType(StrEnum):
    CLS = "CLS"
    MEAN = "MEAN"


@dataclass(frozen=True)
class _ModelSource:
    hf: str | None = None


def _install_fake_fastembed(
    monkeypatch: pytest.MonkeyPatch, *, warning: str | None = None
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    registrations: list[dict[str, object]] = []
    constructions: list[dict[str, object]] = []
    module = types.ModuleType("fastembed")
    description = types.ModuleType("fastembed.common.model_description")

    class TextEmbedding:
        def __init__(self, **kwargs: object) -> None:
            constructions.append(kwargs)
            if warning is not None:
                warnings.warn(warning, UserWarning, stacklevel=2)

        @classmethod
        def add_custom_model(cls, **kwargs: object) -> None:
            registrations.append(kwargs)

    cast(Any, module).TextEmbedding = TextEmbedding
    cast(Any, description).PoolingType = _PoolingType
    cast(Any, description).ModelSource = _ModelSource
    monkeypatch.setitem(sys.modules, "fastembed", module)
    monkeypatch.setitem(sys.modules, "fastembed.common", types.ModuleType("fastembed.common"))
    monkeypatch.setitem(sys.modules, "fastembed.common.model_description", description)
    monkeypatch.setattr(adapter, "_REGISTERED_CUSTOM_MODELS", set())
    return registrations, constructions


@pytest.mark.parametrize("name", ["arctic-l", "e5-small"])
def test_custom_preset_is_registered_once_per_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    registrations, constructions = _install_fake_fastembed(monkeypatch)
    preset = EMBEDDING_PRESETS[name]

    _default_backend_factory(_config(preset, tmp_path), tmp_path / "snapshot")
    _default_backend_factory(_config(preset, tmp_path), tmp_path / "snapshot")

    assert registrations == [
        {
            "model": preset.model_name,
            "pooling": _PoolingType(preset.pooling),
            "normalization": preset.normalization,
            "sources": _ModelSource(hf=preset.repo_id),
            "dim": preset.dimensions,
            "model_file": preset.model_file,
        }
    ]
    assert [item["model_name"] for item in constructions] == [preset.model_name, preset.model_name]
    assert constructions[0]["specific_model_path"] == str(tmp_path / "snapshot")


def test_builtin_preset_is_not_registered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registrations, constructions = _install_fake_fastembed(monkeypatch)

    _default_backend_factory(_config(MINILM, tmp_path), tmp_path / "snapshot")

    assert registrations == []
    assert len(constructions) == 1


MINILM_POOLING_WARNING = (
    "The model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 now uses mean pooling "
    "instead of CLS embedding."
)


def test_default_backend_factory_suppresses_known_fastembed_pooling_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_fastembed(monkeypatch, warning=MINILM_POOLING_WARNING)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _default_backend_factory(_config(MINILM, tmp_path), tmp_path / "snapshot")

    assert [str(item.message) for item in caught] == []


def test_minilm_warning_filter_is_not_applied_to_other_presets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_fastembed(monkeypatch, warning=MINILM_POOLING_WARNING)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _default_backend_factory(_config(E5, tmp_path), tmp_path / "snapshot")

    assert [str(item.message) for item in caught] == [MINILM_POOLING_WARNING]


# text_embeddings_for (A-6) --------------------------------------------------------------------


def _files(root: Path) -> list[Path]:
    return sorted(root.rglob("*"))


def test_text_embeddings_for_without_settings_file_uses_e5_small_and_creates_nothing(tmp_path: Path) -> None:
    catalog_service = CatalogService(graph_home_path=tmp_path / "home")
    before = _files(tmp_path)

    embeddings = text_embeddings_for(catalog_service, local_files_only=True)

    assert embeddings.model_spec() == E5.model_spec()
    assert embeddings.config.cache_dir == Path("~/llm/models").expanduser()
    assert embeddings.config.local_files_only is True
    assert _files(tmp_path) == before


def test_text_embeddings_for_reads_the_settings_file_on_every_call(tmp_path: Path) -> None:
    catalog_service = CatalogService(graph_home_path=tmp_path / "home")
    models = tmp_path / "models"
    save_embedding_selection(catalog_service.embedding_config_path, EmbeddingSelection("e5-small", models))

    first = text_embeddings_for(catalog_service, local_files_only=False)
    save_embedding_selection(catalog_service.embedding_config_path, EmbeddingSelection("minilm", models))
    second = text_embeddings_for(catalog_service, local_files_only=False)

    assert first.model_spec() == E5.model_spec()
    assert first.config.cache_dir == models
    assert first.config.local_files_only is False
    assert second.model_spec() == MINILM.model_spec()
