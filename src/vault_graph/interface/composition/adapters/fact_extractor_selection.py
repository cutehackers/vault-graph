"""The one place that turns fact extraction settings into a `FactExtractor` (spec 2026-11-16 D18).

The real adapters are imported only when an extractor is built, so importing this module does not load the
Claude CLI or `llama-server` code. `tests/conftest.py` replaces `_construct` with a fake extractor and makes
`_load_adapter_class` fail the test, so no test reaches a real extractor through this function.
"""

from __future__ import annotations

import importlib

from vault_graph.errors import CatalogError
from vault_graph.interface.composition.adapters.fact_extractor import FactExtractor
from vault_graph.operation.scope.facts_settings import FactsSettings

REAL_FACT_EXTRACTORS: dict[str, tuple[str, str]] = {
    "claude": ("vault_graph.interface.composition.adapters.claude_fact_extractor", "ClaudeFactExtractor"),
    "llama-server": ("vault_graph.interface.composition.adapters.llama_fact_extractor", "LlamaFactExtractor"),
}
"""Extractor name to (module, class). Each class takes keyword arguments `endpoint` and `model`."""


def select_fact_extractor(settings: FactsSettings) -> FactExtractor:
    """Build the extractor `settings` names. Turned-off settings raise `CatalogError`."""
    if not settings.enabled:
        raise CatalogError("fact extraction is off; run `vg facts on` to turn it on")
    return _construct(settings)


def construct_real_fact_extractor(settings: FactsSettings) -> FactExtractor:
    """Import the adapter class `settings.extractor` names and build it with the settings' endpoint and model."""
    target = REAL_FACT_EXTRACTORS.get(settings.extractor)
    if target is None:
        available = ", ".join(REAL_FACT_EXTRACTORS)
        raise CatalogError(f"unknown fact extractor {settings.extractor!r}; available: {available}")
    adapter_class = _load_adapter_class(*target)
    extractor: FactExtractor = adapter_class(endpoint=settings.endpoint, model=settings.model)
    return extractor


def _load_adapter_class(module_name: str, class_name: str) -> type:
    adapter_class: type = getattr(importlib.import_module(module_name), class_name)
    return adapter_class


_construct = construct_real_fact_extractor
