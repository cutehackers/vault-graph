"""Small, side-effect-free helpers around the pinned Tree-sitter bindings."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Any

from vault_graph.code_index.code_models import (
    CODE_DART_GRAMMAR_PACKAGE_VERSION,
    CODE_TREE_SITTER_ABI_VERSION,
    CODE_TREE_SITTER_PYTHON_VERSION,
    CODE_TREE_SITTER_RUNTIME_VERSION,
    CodeFileInput,
    CodeParseDiagnostic,
)


def file_identity(file: CodeFileInput) -> str:
    return stable_identity("code-file-v1", file.repository_id, file.relative_path)


def stable_identity(*parts: str) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_language(language: str) -> Any:
    """Load only an installed grammar; this function never downloads or caches."""

    normalized = language.casefold()
    if normalized == "python":
        from tree_sitter import Language
        from tree_sitter_python import language as grammar_language
    elif normalized == "dart":
        from tree_sitter import Language
        from tree_sitter_dart import language as grammar_language
    else:
        raise ValueError(f"unsupported parser language: {language}")

    grammar = Language(grammar_language())
    abi_version = getattr(grammar, "abi_version", None)
    if abi_version is None:
        abi_version = getattr(grammar, "version", None)
    if abi_version != CODE_TREE_SITTER_ABI_VERSION:
        raise RuntimeError(
            "installed Tree-sitter grammar ABI does not match the pinned parser spec "
            f"(expected {CODE_TREE_SITTER_ABI_VERSION}, got {abi_version}); "
            "update the runtime and grammar together"
        )
    return grammar


def parse_source(file: CodeFileInput) -> Any:
    from tree_sitter import Parser

    parser = Parser(load_language(file.language))
    return parser.parse(file.content)


def walk(node: Any) -> Iterator[Any]:
    yield node
    for child in node.children:
        yield from walk(child)


def node_text(node: Any) -> str:
    text = node.text
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text)


def node_start(node: Any) -> tuple[int, int]:
    return (node.start_point.row + 1, node.start_point.column)


def node_end(node: Any) -> tuple[int, int]:
    return (node.end_point.row + 1, node.end_point.column)


def syntax_diagnostics(file: CodeFileInput, tree: Any, *, limit: int = 32) -> tuple[CodeParseDiagnostic, ...]:
    diagnostics: list[CodeParseDiagnostic] = []
    for node in walk(tree.root_node):
        if node.type != "ERROR" and not bool(getattr(node, "is_missing", False)):
            continue
        start_line, start_column = node_start(node)
        end_line, end_column = node_end(node)
        code = "syntax-error" if node.type == "ERROR" else "missing-token"
        diagnostic_id = stable_identity(
            "code-diagnostic-v1",
            file.repository_id,
            file.relative_path,
            code,
            str(start_line),
            str(start_column),
            str(end_line),
            str(end_column),
        )
        diagnostics.append(
            CodeParseDiagnostic(
                diagnostic_id=diagnostic_id,
                repository_id=file.repository_id,
                relative_path=file.relative_path,
                severity="error",
                code=code,
                message=f"Tree-sitter reported {node.type} while parsing {file.relative_path}",
                start_line=start_line,
                start_column=start_column,
                end_line=end_line,
                end_column=end_column,
                parser_spec_version=file.parser_spec_version,
            )
        )
        if len(diagnostics) >= limit:
            break
    return tuple(diagnostics)


def unsupported_diagnostics(
    file: CodeFileInput,
    tree: Any,
    unsupported_node_types: frozenset[str],
    *,
    limit: int = 32,
) -> tuple[CodeParseDiagnostic, ...]:
    """Report known grammar constructs outside the adapter's common vocabulary."""

    diagnostics: list[CodeParseDiagnostic] = []
    for node in walk(tree.root_node):
        if node.type not in unsupported_node_types:
            continue
        start_line, start_column = node_start(node)
        end_line, end_column = node_end(node)
        diagnostics.append(
            CodeParseDiagnostic(
                diagnostic_id=stable_identity(
                    "code-diagnostic-v1",
                    file.repository_id,
                    file.relative_path,
                    "unsupported-construct",
                    node.type,
                    str(start_line),
                    str(start_column),
                ),
                repository_id=file.repository_id,
                relative_path=file.relative_path,
                severity="warning",
                code="unsupported-construct",
                message=f"The {file.language} adapter does not project {node.type!r} yet",
                start_line=start_line,
                start_column=start_column,
                end_line=end_line,
                end_column=end_column,
                parser_spec_version=file.parser_spec_version,
            )
        )
        if len(diagnostics) >= limit:
            break
    return tuple(diagnostics)


def source_signature(node: Any, *, max_length: int = 512) -> str:
    """Return declaration text without retaining a complete source body."""

    text = node_text(node).strip()
    for marker in ("\n", "{", "=>"):
        if marker in text:
            text = text.split(marker, 1)[0].rstrip()
    return text[:max_length]


def parser_dependency_versions() -> tuple[str, str, str]:
    return (
        CODE_TREE_SITTER_RUNTIME_VERSION,
        CODE_TREE_SITTER_PYTHON_VERSION,
        CODE_DART_GRAMMAR_PACKAGE_VERSION,
    )
