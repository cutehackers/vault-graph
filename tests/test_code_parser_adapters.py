from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

import pytest

from vault_graph.code_index.code_models import CODE_PARSER_SPEC_VERSION, CODE_TREE_SITTER_ABI_VERSION, CodeFileInput

FIXTURES = Path(__file__).parent / "fixtures" / "code_index"


def _input(path: Path, *, language: str, is_test_file: bool = False) -> CodeFileInput:
    content = path.read_bytes()
    return CodeFileInput(
        repository_id="fixture",
        relative_path=path.relative_to(FIXTURES).as_posix(),
        language=language,
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        source_revision="fixture-revision",
        is_test_file=is_test_file,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )


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


def test_tree_sitter_runtime_and_grammars_share_the_pinned_abi() -> None:
    from vault_graph.code_index.tree_sitter_parsing import load_language

    assert load_language("python").abi_version == CODE_TREE_SITTER_ABI_VERSION
    assert load_language("dart").abi_version == CODE_TREE_SITTER_ABI_VERSION


def test_file_input_is_the_parser_boundary_and_does_not_require_file_io() -> None:
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


def test_python_adapter_extracts_deterministic_symbols_and_raw_references() -> None:
    from vault_graph.code_index.python_parser import PythonCodeParserAdapter

    result = PythonCodeParserAdapter().parse(_input(FIXTURES / "python/basic_project/service.py", language="python"))
    assert {symbol.kind for symbol in result.symbols} >= {"module", "class", "method", "property", "function"}
    names = {symbol.qualified_name for symbol in result.symbols}
    assert "python.basic_project.service.Service" in names
    assert "python.basic_project.service.Service.name" in names
    assert "python.basic_project.service.Service.run" in names
    assert "python.basic_project.service.make_service" in names
    assert all(symbol.parser_spec_version == CODE_PARSER_SPEC_VERSION for symbol in result.symbols)
    assert all(symbol.content_hash == result.file.content_hash for symbol in result.symbols)
    assert {reference.relation_kind for reference in result.references} >= {"CONTAINS", "DEFINES", "IMPORTS", "CALLS"}
    assert result.diagnostics == ()
    assert result == PythonCodeParserAdapter().parse(
        _input(FIXTURES / "python/basic_project/service.py", language="python")
    )


def test_python_adapter_reports_syntax_errors_without_crashing() -> None:
    from vault_graph.code_index.python_parser import PythonCodeParserAdapter

    result = PythonCodeParserAdapter().parse(
        _input(FIXTURES / "python/basic_project/malformed.py.fixture", language="python")
    )
    assert result.diagnostics
    assert any(diagnostic.code == "syntax-error" for diagnostic in result.diagnostics)
    assert all(diagnostic.start_line is None or diagnostic.start_line >= 1 for diagnostic in result.diagnostics)


def test_python_adapter_reports_known_unsupported_constructs() -> None:
    from vault_graph.code_index.python_parser import PythonCodeParserAdapter

    result = PythonCodeParserAdapter().parse(
        _input(FIXTURES / "python/basic_project/unsupported.py", language="python")
    )
    assert any(diagnostic.code == "unsupported-construct" for diagnostic in result.diagnostics)


def test_dart_adapter_extracts_library_declarations_and_annotations() -> None:
    from vault_graph.code_index.dart_parser import DartCodeParserAdapter

    result = DartCodeParserAdapter().parse(_input(FIXTURES / "dart/basic_project/greeter.dart", language="dart"))
    assert {symbol.kind for symbol in result.symbols} >= {"module", "class", "mixin", "method", "property", "test"}
    names = {symbol.qualified_name for symbol in result.symbols}
    assert "sample" in names
    assert "sample.Greeter" in names
    assert "sample.Greeter.greet" in names
    assert "sample.Mixin" in names
    assert any(reference.relation_kind == "EXTENDS" for reference in result.references)
    assert any(reference.relation_kind == "IMPLEMENTS" for reference in result.references)
    assert any(reference.relation_kind == "IMPORTS" for reference in result.references)
    assert result.diagnostics == ()
    assert result == DartCodeParserAdapter().parse(
        _input(FIXTURES / "dart/basic_project/greeter.dart", language="dart")
    )


def test_adapters_reject_a_file_for_the_wrong_language() -> None:
    from vault_graph.code_index.dart_parser import DartCodeParserAdapter

    file = _input(FIXTURES / "python/basic_project/service.py", language="python")
    with pytest.raises(ValueError, match="language"):
        DartCodeParserAdapter().parse(file)
