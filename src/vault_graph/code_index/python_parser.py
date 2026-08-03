"""Tree-sitter based structural extraction for Python source files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vault_graph.code_index.code_models import (
    CODE_PARSER_SPEC_VERSION,
    CodeFileInput,
    CodeParseResult,
    CodeReferenceRecord,
    CodeSymbolRecord,
)
from vault_graph.code_index.tree_sitter_parsing import (
    file_identity,
    node_end,
    node_start,
    node_text,
    parse_source,
    source_signature,
    stable_identity,
    syntax_diagnostics,
    unsupported_diagnostics,
    walk,
)


@dataclass(frozen=True)
class _Declaration:
    node: Any
    name_node: Any
    symbol: CodeSymbolRecord
    parent_symbol_id: str


class PythonCodeParserAdapter:
    """Extract declarations and raw references from one Python file.

    Name resolution is intentionally deferred to the reference resolver. This
    adapter reports only syntax-backed candidates and never searches source
    text for declarations.
    """

    language = "python"
    parser_spec_version = CODE_PARSER_SPEC_VERSION

    def parse(self, file: CodeFileInput) -> CodeParseResult:
        self._validate_input(file)
        tree = parse_source(file)
        file_id = file_identity(file)
        module_name = _module_name(file.relative_path)
        module = self._module_symbol(file, file_id, module_name, tree.root_node)
        declarations: list[_Declaration] = []
        owners: dict[Any, str] = {tree.root_node: module.symbol_id}
        ordinal_counts: dict[tuple[str, str, str], int] = {}
        self._collect_declarations(
            file=file,
            file_id=file_id,
            module_name=module_name,
            node=tree.root_node,
            parent=module,
            declarations=declarations,
            owners=owners,
            ordinal_counts=ordinal_counts,
        )
        symbols = tuple(sorted((module, *(declaration.symbol for declaration in declarations)), key=_symbol_sort_key))
        references = self._collect_references(file, file_id, tree.root_node, module, declarations, owners)
        diagnostics = (
            syntax_diagnostics(file, tree)
            + unsupported_diagnostics(file, tree, frozenset({"match_statement", "type_alias_statement"}))
        )[:32]
        return CodeParseResult(
            file=file.snapshot(),
            symbols=symbols,
            references=references,
            diagnostics=diagnostics,
        )

    def _validate_input(self, file: CodeFileInput) -> None:
        if file.language.casefold() != self.language:
            raise ValueError(f"Python adapter requires language='python', got {file.language!r}")
        if file.parser_spec_version != self.parser_spec_version:
            raise ValueError(
                "file parser_spec_version does not match the installed Python adapter "
                f"({file.parser_spec_version!r} != {self.parser_spec_version!r})"
            )

    def _module_symbol(self, file: CodeFileInput, file_id: str, name: str, node: Any) -> CodeSymbolRecord:
        start_line, start_column = node_start(node)
        end_line, end_column = node_end(node)
        max_line = max(1, file.snapshot().line_count)
        start_line = min(start_line, max_line)
        end_line = max(start_line, min(end_line, max_line))
        return CodeSymbolRecord(
            symbol_id=stable_identity("code-symbol-v1", file.repository_id, file_id, "module", name, "0"),
            repository_id=file.repository_id,
            file_id=file_id,
            kind="module",
            language_kind="module",
            name=name.rsplit(".", 1)[-1],
            qualified_name=name,
            signature=None,
            start_line=start_line,
            end_line=end_line,
            start_column=start_column,
            end_column=end_column,
            content_hash=file.content_hash,
            source_revision=file.source_revision,
            parser_spec_version=file.parser_spec_version,
        )

    def _collect_declarations(
        self,
        *,
        file: CodeFileInput,
        file_id: str,
        module_name: str,
        node: Any,
        parent: CodeSymbolRecord,
        declarations: list[_Declaration],
        owners: dict[Any, str],
        ordinal_counts: dict[tuple[str, str, str], int],
    ) -> None:
        if node.type == "decorated_definition":
            declaration_node = next(
                (child for child in node.named_children if child.type in {"class_definition", "function_definition"}),
                None,
            )
            if declaration_node is not None:
                declaration = self._build_declaration(
                    file,
                    file_id,
                    module_name,
                    declaration_node,
                    node,
                    parent,
                    ordinal_counts,
                )
                declarations.append(declaration)
                owners[node] = declaration.symbol.symbol_id
                owners[declaration_node] = declaration.symbol.symbol_id
                for child in declaration_node.children:
                    self._collect_declarations(
                        file=file,
                        file_id=file_id,
                        module_name=module_name,
                        node=child,
                        parent=declaration.symbol,
                        declarations=declarations,
                        owners=owners,
                        ordinal_counts=ordinal_counts,
                    )
                return
        if node.type in {"class_definition", "function_definition"}:
            declaration = self._build_declaration(file, file_id, module_name, node, node, parent, ordinal_counts)
            declarations.append(declaration)
            owners[node] = declaration.symbol.symbol_id
            for child in node.children:
                self._collect_declarations(
                    file=file,
                    file_id=file_id,
                    module_name=module_name,
                    node=child,
                    parent=declaration.symbol,
                    declarations=declarations,
                    owners=owners,
                    ordinal_counts=ordinal_counts,
                )
            return
        for child in node.children:
            self._collect_declarations(
                file=file,
                file_id=file_id,
                module_name=module_name,
                node=child,
                parent=parent,
                declarations=declarations,
                owners=owners,
                ordinal_counts=ordinal_counts,
            )

    def _build_declaration(
        self,
        file: CodeFileInput,
        file_id: str,
        module_name: str,
        declaration_node: Any,
        span_node: Any,
        parent: CodeSymbolRecord,
        ordinal_counts: dict[tuple[str, str, str], int],
    ) -> _Declaration:
        name_node = next((child for child in declaration_node.named_children if child.type == "identifier"), None)
        if name_node is None:
            raise ValueError(f"Tree-sitter declaration has no identifier: {declaration_node.type}")
        name = node_text(name_node)
        is_property = span_node.type == "decorated_definition" and any(
            "property" in node_text(child).casefold() for child in span_node.named_children if child.type == "decorator"
        )
        is_test = _is_test_name(name, file)
        if declaration_node.type == "class_definition":
            kind = "class"
        elif is_property:
            kind = "property"
        elif is_test:
            kind = "test"
        elif parent.kind == "class":
            kind = "method"
        else:
            kind = "function"
        qualified_name = f"{parent.qualified_name}.{name}"
        ordinal_key = (parent.symbol_id, kind, name)
        ordinal = ordinal_counts.get(ordinal_key, 0)
        ordinal_counts[ordinal_key] = ordinal + 1
        start_line, start_column = node_start(span_node)
        end_line, end_column = node_end(span_node)
        symbol_id = stable_identity(
            "code-symbol-v1",
            file.repository_id,
            file_id,
            kind,
            qualified_name,
            str(ordinal),
        )
        symbol = CodeSymbolRecord(
            symbol_id=symbol_id,
            repository_id=file.repository_id,
            file_id=file_id,
            kind=kind,
            language_kind=declaration_node.type,
            name=name,
            qualified_name=qualified_name,
            signature=source_signature(declaration_node),
            start_line=start_line,
            end_line=end_line,
            start_column=start_column,
            end_column=end_column,
            content_hash=file.content_hash,
            source_revision=file.source_revision,
            parser_spec_version=file.parser_spec_version,
        )
        return _Declaration(span_node, name_node, symbol, parent.symbol_id)

    def _collect_references(
        self,
        file: CodeFileInput,
        file_id: str,
        root: Any,
        module: CodeSymbolRecord,
        declarations: list[_Declaration],
        owners: dict[Any, str],
    ) -> tuple[CodeReferenceRecord, ...]:
        symbols_by_id = {module.symbol_id: module, **{d.symbol.symbol_id: d.symbol for d in declarations}}
        references: list[CodeReferenceRecord] = []

        def add(node: Any, relation: str, target: str, source_symbol_id: str | None) -> None:
            start_line, start_column = node_start(node)
            reference_id = stable_identity(
                "code-reference-v1",
                file.repository_id,
                file_id,
                source_symbol_id or "",
                relation,
                target,
                str(start_line),
                str(start_column),
            )
            references.append(
                CodeReferenceRecord(
                    reference_id=reference_id,
                    repository_id=file.repository_id,
                    source_file_id=file_id,
                    source_symbol_id=source_symbol_id,
                    relation_kind=relation,
                    target_key=target,
                    anchor_start_line=start_line,
                    anchor_start_column=start_column,
                    parser_spec_version=file.parser_spec_version,
                )
            )

        def owner(node: Any) -> str:
            current = node
            while current is not None:
                found = owners.get(current)
                if found is not None:
                    return found
                current = current.parent
            return module.symbol_id

        if file.snapshot().line_count > 0 and node_start(root)[0] <= file.snapshot().line_count:
            add(root, "DEFINES", module.qualified_name, None)
        for declaration in declarations:
            add(declaration.node, "DEFINES", declaration.symbol.qualified_name, declaration.parent_symbol_id)
            add(declaration.node, "CONTAINS", declaration.symbol.qualified_name, declaration.parent_symbol_id)

        for node in walk(root):
            source_symbol_id = owner(node)
            if node.type in {"import_statement", "import_from_statement"}:
                for target in _python_import_targets(node):
                    add(node, "IMPORTS", target, source_symbol_id)
            elif node.type == "call":
                target = _python_call_target(node)
                if target:
                    add(node, "CALLS", target, source_symbol_id)
                    source_symbol = symbols_by_id[source_symbol_id]
                    if source_symbol.kind == "test":
                        add(node, "TESTS", target, source_symbol_id)
            elif node.type == "class_definition":
                for target_node in _python_base_nodes(node):
                    target = node_text(target_node)
                    if target:
                        add(target_node, "EXTENDS", target, source_symbol_id)
        return tuple(sorted(references, key=_reference_sort_key))


PythonParserAdapter = PythonCodeParserAdapter


def _module_name(relative_path: str) -> str:
    path = relative_path.replace("\\", "/")
    if path.endswith(".py"):
        path = path[:-3]
    if path.endswith("/__init__"):
        path = path[: -len("/__init__")]
    return path.strip("/").replace("/", ".") or "module"


def _is_test_name(name: str, file: CodeFileInput) -> bool:
    return file.is_test_file or name.startswith("test_") or name.startswith("test")


def _python_import_targets(node: Any) -> tuple[str, ...]:
    named = list(node.named_children)
    if node.type == "import_from_statement":
        return (node_text(named[0]),) if named else ()
    targets: list[str] = []
    for child in named:
        if child.type == "dotted_name":
            targets.append(node_text(child))
        elif child.type == "aliased_import":
            dotted = next((descendant for descendant in walk(child) if descendant.type == "dotted_name"), None)
            if dotted is not None:
                targets.append(node_text(dotted))
    return tuple(targets)


def _python_call_target(node: Any) -> str:
    callee = node.named_children[0] if node.named_children else None
    if callee is None:
        return ""
    if callee.type in {"attribute", "identifier", "dotted_name"}:
        identifiers = [child for child in walk(callee) if child.type == "identifier"]
        return node_text(identifiers[-1] if identifiers else callee)
    return node_text(callee).split(".")[-1]


def _python_base_nodes(node: Any) -> tuple[Any, ...]:
    argument_list = next((child for child in node.named_children if child.type == "argument_list"), None)
    if argument_list is None:
        return ()
    return tuple(
        child for child in argument_list.named_children if child.type not in {"keyword_argument", "list_splat"}
    )


def _symbol_sort_key(symbol: CodeSymbolRecord) -> tuple[int, int, str, str]:
    return (symbol.start_line, symbol.start_column, symbol.qualified_name, symbol.kind)


def _reference_sort_key(reference: CodeReferenceRecord) -> tuple[int, int, str, str, str]:
    return (
        reference.anchor_start_line,
        reference.anchor_start_column,
        reference.relation_kind,
        reference.source_symbol_id or "",
        reference.target_key,
    )
