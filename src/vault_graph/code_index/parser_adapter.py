"""Stable parser boundary for language-specific code projection adapters."""

from __future__ import annotations

from typing import Protocol

from vault_graph.code_index.code_models import CodeFileInput, CodeParseResult


class CodeParserAdapter(Protocol):
    """Parse one already-read source file without filesystem or process I/O."""

    language: str
    parser_spec_version: str

    def parse(self, file: CodeFileInput) -> CodeParseResult:
        """Return deterministic structural records and bounded diagnostics."""
