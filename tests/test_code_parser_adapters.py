from __future__ import annotations

import importlib
import sys

from vault_graph.code_index.code_models import (
    CODE_DART_GRAMMAR_REVISION,
    CODE_PARSER_SPEC_VERSION,
    CodeFileInput,
)


def test_parser_spec_identifies_installed_grammars_without_network_side_effects() -> None:
    assert CODE_PARSER_SPEC_VERSION.startswith("code-parser-spec-")
    assert CODE_DART_GRAMMAR_REVISION.startswith("tree-sitter-dart-")

    before = set(sys.modules)
    module = importlib.import_module("vault_graph.code_index.code_models")
    after = set(sys.modules)
    assert module.CODE_PARSER_SPEC_VERSION == CODE_PARSER_SPEC_VERSION
    assert "watchfiles" not in (after - before)


def test_file_input_is_the_parser_boundary_and_does_not_require_file_io() -> None:
    file = CodeFileInput(
        repository_id="demo",
        relative_path="lib/example.py",
        language="python",
        content=b"def hello():\n    return 1\n",
        content_hash="a" * 64,
        source_revision="content-hash:a",
        is_test_file=False,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )

    assert file.content.startswith(b"def")
    assert file.relative_path == "lib/example.py"
