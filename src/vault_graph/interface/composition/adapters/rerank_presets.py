"""Rerank model presets and the pinned-snapshot lookup for their files.

Only `vg reranker use` calls `download_rerank_model`. Search finds the files with `local_files_only=True`
through `rerank_model_downloaded` or `resolve_rerank_snapshot`. Importing this module loads no model library.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from vault_graph.retrieval.search.reranker import RerankerUnavailableError


class RerankModelUnavailableError(RerankerUnavailableError):
    """The preset's pinned files are not in the model folder, or downloading them failed."""


@dataclass(frozen=True)
class RerankPreset:
    """One entry of the rerank model list. Adding a model means adding one entry to ``RERANK_PRESETS``."""

    name: str
    model_name: str
    repo_id: str
    revision: str
    model_file: str
    files: tuple[str, ...]
    file_bytes: Mapping[str, int]
    download_mb: int
    license: str
    summary: str


# Pinned and measured in docs/design/reports/2026-11-reranker-measurement.md §2 (spec 2026-11-13 D5, D18).
# The arm64 int8 file is the only ONNX file listed. x86 files are out of scope for this spec.
_MMARCO_FILE_BYTES: Mapping[str, int] = MappingProxyType(
    {
        "onnx/model_qint8_arm64.onnx": 118_620_017,
        "tokenizer.json": 17_082_660,
        "config.json": 891,
        "tokenizer_config.json": 435,
        "special_tokens_map.json": 239,
    }
)

RERANK_PRESETS: Mapping[str, RerankPreset] = MappingProxyType(
    {
        preset.name: preset
        for preset in (
            RerankPreset(
                name="mmarco",
                model_name="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
                repo_id="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
                revision="1427fd652930e4ba29e8149678df786c240d8825",
                model_file="onnx/model_qint8_arm64.onnx",
                files=(
                    "onnx/model_qint8_arm64.onnx",
                    "config.json",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "special_tokens_map.json",
                ),
                file_bytes=_MMARCO_FILE_BYTES,
                download_mb=136,
                license="apache-2.0",
                summary="Multilingual MiniLM cross-encoder, Apple Silicon int8",
            ),
        )
    }
)


def rerank_model_downloaded(preset: RerankPreset, models_dir: Path) -> bool:
    """Return whether `models_dir` already holds the preset's pinned files. Never downloads."""
    try:
        resolve_rerank_snapshot(preset, models_dir, local_files_only=True)
    except RerankModelUnavailableError:
        return False
    return True


def download_rerank_model(preset: RerankPreset, models_dir: Path) -> Path:
    """Download the preset's pinned files into `models_dir` and return the snapshot folder."""
    return resolve_rerank_snapshot(preset, models_dir, local_files_only=False)


def resolve_rerank_snapshot(preset: RerankPreset, models_dir: Path, *, local_files_only: bool) -> Path:
    """Return the snapshot folder of the preset's pinned revision in `models_dir`.

    Search must pass `local_files_only=True`. Any failure raises `RerankModelUnavailableError`.
    """
    try:
        from huggingface_hub import snapshot_download

        return Path(
            snapshot_download(
                repo_id=preset.repo_id,
                revision=preset.revision,
                cache_dir=str(models_dir.expanduser()),
                local_files_only=local_files_only,
                allow_patterns=list(preset.files),
            )
        )
    except Exception as exc:  # noqa: BLE001 - converted to a domain error naming the model
        raise RerankModelUnavailableError(f"reranker model {preset.name!r} unavailable: {exc}") from exc
