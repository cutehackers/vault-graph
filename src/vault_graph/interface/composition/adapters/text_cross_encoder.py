"""fastembed `TextCrossEncoder` behind the `Reranker` port (spec 2026-11-13 cross-encoder-rerank D14, I2, F6).

`TextCrossEncoderReranker` finds the preset's pinned snapshot with `local_files_only=True` on the first
rerank and never downloads or falls back to another model. It cuts each query and text pair to 256 tokens
before scoring. Importing this module loads no model library.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol

from vault_graph.interface.composition.adapters.rerank_presets import (
    RerankModelUnavailableError,
    RerankPreset,
    resolve_rerank_snapshot,
)
from vault_graph.retrieval.search.reranker import RerankError

# fastembed cuts pairs only at the model's 512 and pads a batch to its longest pair (spec D7, X32).
MAX_PAIR_TOKENS = 256
MAX_QUERY_TOKENS = 128
# <s> query </s></s> text </s> for the XLM-R tokenizer of mmarco.
PAIR_SPECIAL_TOKENS = 4


class CrossEncoder(Protocol):
    def rerank(self, query: str, documents: Iterable[str]) -> Iterable[float]: ...


class TokenEncoding(Protocol):
    @property
    def offsets(self) -> list[tuple[int, int]]: ...


class PairTokenizer(Protocol):
    def encode(self, text: str, /, *, add_special_tokens: bool = ...) -> TokenEncoding: ...


SnapshotResolver = Callable[[RerankPreset, Path], Path]
EncoderFactory = Callable[[RerankPreset, Path], CrossEncoder]
TokenizerLoader = Callable[[Path], PairTokenizer]


class TextCrossEncoderReranker:
    """`Reranker` over one rerank preset. The model loads on the first `rerank` call."""

    def __init__(
        self,
        preset: RerankPreset,
        models_dir: Path,
        *,
        snapshot_resolver: SnapshotResolver | None = None,
        encoder_factory: EncoderFactory | None = None,
        tokenizer_loader: TokenizerLoader | None = None,
    ) -> None:
        self._preset = preset
        self._models_dir = models_dir
        self._snapshot_resolver = snapshot_resolver or _local_snapshot
        self._encoder_factory = encoder_factory or default_encoder_factory
        self._tokenizer_loader = tokenizer_loader or default_tokenizer_loader
        self._lock = threading.Lock()
        self._snapshot: Path | None = None
        self._unavailable: RerankModelUnavailableError | None = None
        self._loaded: tuple[CrossEncoder, PairTokenizer] | None = None

    @property
    def preset(self) -> str:
        return self._preset.name

    def rerank(self, query: str, passages: Sequence[str]) -> list[int]:
        """Indices into ``passages``, highest model score first.

        Raises `RerankModelUnavailableError` when the pinned files are missing, and `RerankError` for any
        tokenizer, ONNX, or inference failure.
        """
        if not passages:
            return []
        encoder, tokenizer = self._load()
        try:
            query, texts = _cut_pairs(tokenizer, query, passages)
            scores = [float(score) for score in encoder.rerank(query, texts)]
        except Exception as exc:  # noqa: BLE001 - converted to the port's error
            raise RerankError(f"reranker {self.preset!r} failed: {exc}") from exc
        if len(scores) != len(passages):
            raise RerankError(f"reranker {self.preset!r} returned {len(scores)} scores for {len(passages)} passages")
        return sorted(range(len(scores)), key=lambda index: (-scores[index], index))

    def _load(self) -> tuple[CrossEncoder, PairTokenizer]:
        with self._lock:
            if self._loaded is not None:
                return self._loaded
            if self._unavailable is not None:
                raise self._unavailable
            if self._snapshot is None:
                try:
                    self._snapshot = self._snapshot_resolver(self._preset, self._models_dir)
                except RerankModelUnavailableError as exc:
                    self._unavailable = exc
                    raise
            try:
                self._loaded = (
                    self._encoder_factory(self._preset, self._snapshot),
                    self._tokenizer_loader(self._snapshot),
                )
            except Exception as exc:  # noqa: BLE001 - converted to the port's error, retried next time
                raise RerankError(f"reranker {self.preset!r} could not load: {exc}") from exc
            return self._loaded


def _local_snapshot(preset: RerankPreset, models_dir: Path) -> Path:
    return resolve_rerank_snapshot(preset, models_dir, local_files_only=True)


def _cut_pairs(tokenizer: PairTokenizer, query: str, passages: Sequence[str]) -> tuple[str, list[str]]:
    """Cut the text first so each pair fits; cut the query to `MAX_QUERY_TOKENS` only if it alone is too long."""
    budget = MAX_PAIR_TOKENS - PAIR_SPECIAL_TOKENS
    query_offsets = tokenizer.encode(query, add_special_tokens=False).offsets
    if len(query_offsets) > budget:
        query = _cut(query, query_offsets, MAX_QUERY_TOKENS)
        query_tokens = MAX_QUERY_TOKENS
    else:
        query_tokens = len(query_offsets)
    text_budget = budget - query_tokens
    texts = [_cut(text, tokenizer.encode(text, add_special_tokens=False).offsets, text_budget) for text in passages]
    return query, texts


def _cut(text: str, offsets: Sequence[tuple[int, int]], limit: int) -> str:
    if len(offsets) <= limit:
        return text
    if limit <= 0:
        return ""
    return text[: offsets[limit - 1][1]]


def default_encoder_factory(preset: RerankPreset, snapshot: Path) -> CrossEncoder:
    """Build fastembed's `TextCrossEncoder` from the snapshot folder. It never downloads."""
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    _register_custom_model(TextCrossEncoder, preset)
    encoder: CrossEncoder = TextCrossEncoder(
        model_name=preset.model_name,
        specific_model_path=str(snapshot),
        # An existing folder, so fastembed does not create its default cache folder (spec I4).
        cache_dir=str(snapshot),
        local_files_only=True,
    )
    return encoder


def default_tokenizer_loader(snapshot: Path) -> PairTokenizer:
    """The model's own tokenizer, without the padding or truncation set in ``tokenizer.json``."""
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(snapshot / "tokenizer.json"))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return tokenizer


_REGISTRATION_LOCK = threading.Lock()
_REGISTERED_MODELS: set[str] = set()


def _register_custom_model(text_cross_encoder: Any, preset: RerankPreset) -> None:
    """Register the preset with fastembed once per process. A second registration raises `ValueError`."""
    from fastembed.common.model_description import ModelSource

    with _REGISTRATION_LOCK:
        if preset.model_name in _REGISTERED_MODELS:
            return
        text_cross_encoder.add_custom_model(
            model=preset.model_name,
            sources=ModelSource(hf=preset.repo_id),
            model_file=preset.model_file,
            license=preset.license,
            size_in_gb=round(preset.download_mb / 1024, 3),
        )
        _REGISTERED_MODELS.add(preset.model_name)
