from __future__ import annotations

import hashlib
import importlib
import sys


def test_parser_spec_identifies_installed_grammars_without_network_side_effects() -> None:
    for name in tuple(sys.modules):
        if name == "vault_graph.code_index" or name.startswith("vault_graph.code_index."):
            del sys.modules[name]
    before = set(sys.modules)
    module = importlib.import_module("vault_graph.code_index.code_models")
    after = set(sys.modules)

    assert module.CODE_PARSER_SPEC_VERSION.startswith("code-parser-spec-")
    assert module.CODE_DART_GRAMMAR_SOURCE == "https://github.com/efrenbl/tree-sitter-dart"
    assert module.CODE_DART_GRAMMAR_SOURCE_REVISION == "12ba73fbfd0755652d97bd10e76a84c076112d14"
    assert module.CODE_DART_GRAMMAR_REVISION == (
        "tree-sitter-dart-0.1.0@12ba73fbfd0755652d97bd10e76a84c076112d14-abi15"
    )
    assert "12ba73fbfd0755652d97bd10e76a84c076112d14" in module.CODE_PARSER_SPEC_VERSION
    assert not any(name == "watchfiles" or name.startswith("tree_sitter") for name in after - before)


def test_file_input_is_the_parser_boundary_and_does_not_require_file_io() -> None:
    from vault_graph.code_index.code_models import CODE_PARSER_SPEC_VERSION, CodeFileInput

    content = b"def hello():\n    return 1\n"
    file = CodeFileInput(
        repository_id="demo",
        relative_path="lib/example.py",
        language="python",
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        source_revision="content-hash:valid",
        is_test_file=False,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )

    assert file.content.startswith(b"def")
    assert file.relative_path == "lib/example.py"
