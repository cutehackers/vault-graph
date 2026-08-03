"""Tree-sitter based structural extraction for Dart source files."""

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


class DartCodeParserAdapter:
    """Extract Dart declarations and syntax-backed reference candidates."""

    language = "dart"
    parser_spec_version = CODE_PARSER_SPEC_VERSION

    def parse(self, file: CodeFileInput) -> CodeParseResult:
        self._validate_input(file)
        tree = parse_source(file)
        file_id = file_identity(file)
        module_name, module_node = _dart_module_identity(file, tree.root_node)
        module = self._module_symbol(file, file_id, module_name, module_node)
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
        symbols = tuple(sorted((module, *(item.symbol for item in declarations)), key=_symbol_sort_key))
        references = self._collect_references(file, file_id, tree.root_node, module, declarations, owners)
        diagnostics = (
            syntax_diagnostics(file, tree)
            + unsupported_diagnostics(
                file,
                tree,
                frozenset({"record_declaration", "record_type", "enum_declaration", "type_alias"}),
            )
            + unsupported_diagnostics(
                file,
                tree,
                frozenset({"initialized_identifier_list", "static_final_declaration_list"}),
                top_level_only=True,
            )
        )[:32]
        return CodeParseResult(
            file=file.snapshot(),
            symbols=symbols,
            references=references,
            diagnostics=diagnostics,
        )

    def _validate_input(self, file: CodeFileInput) -> None:
        if file.language.casefold() != self.language:
            raise ValueError(f"Dart adapter requires language='dart', got {file.language!r}")
        if file.parser_spec_version != self.parser_spec_version:
            raise ValueError(
                "file parser_spec_version does not match the installed Dart adapter "
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
            language_kind="library_name" if node.type == "library_name" else "module",
            name=name.rsplit(".", 1)[-1],
            qualified_name=name,
            signature=source_signature(node) if node.type == "library_name" else None,
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
        if node.type in {"class_definition", "mixin_declaration", "extension_declaration"}:
            name_node = _declaration_name(node)
            if name_node is not None:
                kind = {
                    "class_definition": "class",
                    "mixin_declaration": "mixin",
                    "extension_declaration": "interface",
                }[node.type]
                declaration = self._build_declaration(
                    file,
                    file_id,
                    name_node,
                    node,
                    parent,
                    kind,
                    end_node=_following_body(node),
                    ordinal_counts=ordinal_counts,
                )
                declarations.append(declaration)
                owners[node] = declaration.symbol.symbol_id
                _map_following_body(node, declaration.symbol.symbol_id, owners)
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
        if node.type == "method_signature" and parent.kind in {"class", "mixin", "interface"}:
            name_node = _declaration_name(node)
            name_override = None
            special_name = _special_method_name(node)
            if special_name is not None:
                name_node = special_name[0]
                name_override = special_name[1]
            if name_node is not None:
                kind = (
                    "property"
                    if any(child.type in {"getter_signature", "setter_signature"} for child in node.named_children)
                    else "method"
                )
                declaration = self._build_declaration(
                    file,
                    file_id,
                    name_node,
                    node,
                    parent,
                    kind,
                    end_node=_following_body(node),
                    ordinal_counts=ordinal_counts,
                    name_override=name_override,
                )
                declarations.append(declaration)
                owners[node] = declaration.symbol.symbol_id
                _map_following_body(node, declaration.symbol.symbol_id, owners)
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
        if node.type == "constructor_signature" and parent.kind in {"class", "mixin", "interface"}:
            name_node = _declaration_name(node)
            if name_node is not None:
                declaration = self._build_declaration(
                    file, file_id, name_node, node, parent, "method", ordinal_counts=ordinal_counts
                )
                declarations.append(declaration)
                owners[node] = declaration.symbol.symbol_id
                return
        if node.type == "declaration" and parent.kind in {"class", "mixin", "interface"}:
            constructor = next((child for child in node.named_children if child.type == "constructor_signature"), None)
            if constructor is not None:
                name_node = _constructor_name(constructor)
                if name_node is not None:
                    declaration = self._build_declaration(
                        file,
                        file_id,
                        name_node,
                        constructor,
                        parent,
                        "method",
                        ordinal_counts=ordinal_counts,
                    )
                    declarations.append(declaration)
                    owners[constructor] = declaration.symbol.symbol_id
                return
            for property_node, name_node in _property_declarations(node):
                declaration = self._build_declaration(
                    file,
                    file_id,
                    name_node,
                    property_node,
                    parent,
                    "property",
                    ordinal_counts=ordinal_counts,
                )
                declarations.append(declaration)
                owners[property_node] = declaration.symbol.symbol_id
            return
        if node.type == "function_signature" and node.parent is not None and node.parent.type != "method_signature":
            name_node = _declaration_name(node)
            if name_node is not None:
                kind = "test" if _is_test_name(node_text(name_node), file) else "function"
                declaration = self._build_declaration(
                    file,
                    file_id,
                    name_node,
                    node,
                    parent,
                    kind,
                    end_node=_following_body(node),
                    ordinal_counts=ordinal_counts,
                )
                declarations.append(declaration)
                owners[node] = declaration.symbol.symbol_id
                _map_following_body(node, declaration.symbol.symbol_id, owners)
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
        name_node: Any,
        span_node: Any,
        parent: CodeSymbolRecord,
        kind: str,
        ordinal_counts: dict[tuple[str, str, str], int],
        end_node: Any | None = None,
        name_override: str | None = None,
    ) -> _Declaration:
        name = name_override or node_text(name_node)
        qualified_name = f"{parent.qualified_name}.{name}"
        ordinal_key = (parent.symbol_id, kind, name)
        ordinal = ordinal_counts.get(ordinal_key, 0)
        ordinal_counts[ordinal_key] = ordinal + 1
        start_line, start_column = node_start(span_node)
        end_line, end_column = node_end(end_node or span_node)
        symbol = CodeSymbolRecord(
            symbol_id=stable_identity(
                "code-symbol-v1", file.repository_id, file_id, kind, qualified_name, str(ordinal)
            ),
            repository_id=file.repository_id,
            file_id=file_id,
            kind=kind,
            language_kind=span_node.type,
            name=name,
            qualified_name=qualified_name,
            signature=source_signature(span_node),
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
        symbols_by_id = {module.symbol_id: module, **{item.symbol.symbol_id: item.symbol for item in declarations}}
        references: list[CodeReferenceRecord] = []

        def owner(node: Any) -> str:
            current = node
            while current is not None:
                found = owners.get(current)
                if found is not None:
                    return found
                current = current.parent
            return module.symbol_id

        def add(node: Any, relation: str, target: str, source_symbol_id: str | None) -> None:
            start_line, start_column = node_start(node)
            references.append(
                CodeReferenceRecord(
                    reference_id=stable_identity(
                        "code-reference-v1",
                        file.repository_id,
                        file_id,
                        source_symbol_id or "",
                        relation,
                        target,
                        str(start_line),
                        str(start_column),
                    ),
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

        if file.snapshot().line_count > 0 and node_start(root)[0] <= file.snapshot().line_count:
            add(root, "DEFINES", module.qualified_name, None)
        for declaration in declarations:
            add(declaration.node, "DEFINES", declaration.symbol.qualified_name, declaration.parent_symbol_id)
            add(declaration.node, "CONTAINS", declaration.symbol.qualified_name, declaration.parent_symbol_id)

        for node in walk(root):
            source_symbol_id = owner(node)
            if node.type == "import_specification":
                target = _dart_import_target(node)
                if target:
                    add(node, "IMPORTS", target, source_symbol_id)
            elif node.type in {"class_definition", "mixin_declaration", "extension_declaration"}:
                for relation, target_node in _dart_inheritance_nodes(node):
                    add(target_node, relation, node_text(target_node), source_symbol_id)
            elif node.type in {"new_expression", "const_object_expression"}:
                target = _dart_constructor_call_target(node)
                if target:
                    add(node, "CALLS", target, source_symbol_id)
                    source_symbol = symbols_by_id[source_symbol_id]
                    if source_symbol.kind == "test":
                        add(node, "TESTS", target, source_symbol_id)
            elif node.type == "selector" and _dart_selector_is_call(node):
                target = _dart_constructor_call_target(node) or _dart_call_target(node)
                if target:
                    add(node, "CALLS", target, source_symbol_id)
                    source_symbol = symbols_by_id[source_symbol_id]
                    if source_symbol.kind == "test":
                        add(node, "TESTS", target, source_symbol_id)
        return tuple(sorted(references, key=_reference_sort_key))


DartParserAdapter = DartCodeParserAdapter


def _dart_module_identity(file: CodeFileInput, root: Any) -> tuple[str, Any]:
    library_node = next((node for node in walk(root) if node.type == "library_name"), None)
    if library_node is not None:
        dotted = next((child for child in library_node.named_children if child.type == "dotted_identifier_list"), None)
        return (
            node_text(dotted) if dotted is not None else node_text(library_node).removeprefix("library").strip(" ;"),
            library_node,
        )
    path = file.relative_path.replace("\\", "/")
    return (path.rsplit("/", 1)[-1].removesuffix(".dart") or "module", root)


def _declaration_name(node: Any) -> Any | None:
    direct_identifiers = [child for child in node.named_children if child.type == "identifier"]
    if direct_identifiers:
        return direct_identifiers[-1]
    direct_types = [child for child in node.named_children if child.type == "type_identifier"]
    if direct_types:
        return direct_types[-1]
    descendants = [child for child in walk(node) if child is not node and child.type == "identifier"]
    parameter_list = next((child for child in walk(node) if child.type == "formal_parameter_list"), None)
    if parameter_list is not None:
        before_parameters = [child for child in descendants if child.end_byte <= parameter_list.start_byte]
        if before_parameters:
            return before_parameters[-1]
    if descendants:
        return descendants[-1]
    type_descendants = [child for child in walk(node) if child is not node and child.type == "type_identifier"]
    if type_descendants:
        return type_descendants[-1]
    return None


def _property_declarations(node: Any) -> tuple[tuple[Any, Any], ...]:
    declarations: list[tuple[Any, Any]] = []
    identifier_lists = [child for child in node.named_children if child.type == "initialized_identifier_list"]
    for identifier_list in identifier_lists:
        for property_node in identifier_list.named_children:
            if property_node.type != "initialized_identifier":
                continue
            name_node = next((child for child in property_node.named_children if child.type == "identifier"), None)
            if name_node is not None:
                declarations.append((property_node, name_node))
    return tuple(declarations)


def _constructor_name(node: Any) -> Any | None:
    identifiers = [child for child in node.named_children if child.type == "identifier"]
    return identifiers[-1] if identifiers else None


def _special_method_name(node: Any) -> tuple[Any, str] | None:
    setter_signature = next((child for child in walk(node) if child.type == "setter_signature"), None)
    if setter_signature is not None:
        name_node = next((child for child in setter_signature.named_children if child.type == "identifier"), None)
        if name_node is not None:
            return (name_node, node_text(name_node))
    factory_signature = next((child for child in walk(node) if child.type == "factory_constructor_signature"), None)
    if factory_signature is not None:
        identifiers = [child for child in factory_signature.named_children if child.type == "identifier"]
        if identifiers:
            name_node = identifiers[-1]
            return (name_node, node_text(name_node))
    operator_signature = next((child for child in walk(node) if child.type == "operator_signature"), None)
    if operator_signature is None:
        return None
    token = next(
        (child for child in operator_signature.children if child.type not in {"operator", "formal_parameter_list"}),
        None,
    )
    if token is None:
        return None
    return (token, f"operator {node_text(token)}")


def _is_test_name(name: str, file: CodeFileInput) -> bool:
    return file.is_test_file or name.startswith("test")


def _map_following_body(node: Any, symbol_id: str, owners: dict[Any, str]) -> None:
    body = _following_body(node)
    if body is not None:
        owners[body] = symbol_id


def _following_body(node: Any) -> Any | None:
    parent = node.parent
    if parent is None:
        return None
    children = list(parent.children)
    try:
        index = children.index(node)
    except ValueError:
        return None
    for sibling in children[index + 1 :]:
        if sibling.type == "function_body":
            return sibling
        if sibling.type not in {"comment", ";"}:
            return None
    return None


def _dart_import_target(node: Any) -> str:
    uri = next((child for child in walk(node) if child.type == "uri"), None)
    if uri is None:
        return ""
    return node_text(uri).strip("\"'")


def _dart_inheritance_nodes(node: Any) -> tuple[tuple[str, Any], ...]:
    result: list[tuple[str, Any]] = []
    if node.type in {"mixin_declaration", "extension_declaration"}:
        type_node = next((child for child in node.named_children if child.type == "type_identifier"), None)
        if type_node is not None:
            result.append(("IMPLEMENTS", type_node))
        return tuple(result)
    superclass = next((child for child in node.named_children if child.type == "superclass"), None)
    if superclass is not None:
        base = next((child for child in superclass.named_children if child.type == "type_identifier"), None)
        if base is not None:
            result.append(("EXTENDS", base))
        mixins = next((child for child in superclass.named_children if child.type == "mixins"), None)
        if mixins is not None:
            result.extend(("IMPLEMENTS", child) for child in mixins.named_children if child.type == "type_identifier")
    interfaces = next((child for child in node.named_children if child.type == "interfaces"), None)
    if interfaces is not None:
        result.extend(("IMPLEMENTS", child) for child in interfaces.named_children if child.type == "type_identifier")
    return tuple(result)


def _dart_selector_is_call(node: Any) -> bool:
    return any(child.type == "argument_part" for child in walk(node))


def _dart_constructor_call_target(node: Any) -> str:
    parts = [node_text(child) for child in node.named_children if child.type in {"type_identifier", "identifier"}]
    if parts:
        return ".".join(parts)
    if node.type != "selector":
        return ""
    chain = _dart_selector_chain(node)
    if len(chain) >= 2 and any(part[:1].isupper() for part in chain[-2:]):
        return ".".join(chain)
    return ""


def _dart_selector_chain(node: Any) -> list[str]:
    parent = node.parent
    if parent is None:
        return []
    try:
        index = next(index for index, child in enumerate(parent.children) if child == node)
    except StopIteration:
        return []
    parts: list[str] = []
    for child in parent.children[:index]:
        if child.type in {"identifier", "type_identifier"}:
            parts.append(node_text(child))
        elif child.type == "selector":
            text = node_text(child).lstrip(".")
            if text and text != "()":
                parts.append(text)
    return parts


def _dart_call_target(node: Any) -> str:
    parent = node.parent
    if parent is not None:
        index = next((index for index, child in enumerate(parent.children) if child == node), -1)
        if index > 0:
            previous = parent.children[index - 1]
            if _contains_anonymous_function(previous):
                return ""
            if previous.type in {"identifier", "type_identifier"}:
                return node_text(previous)
            previous_ids = _callee_identifiers(previous)
            if previous_ids:
                return node_text(previous_ids[-1])
    identifiers = _callee_identifiers(node)
    if identifiers:
        return node_text(identifiers[-1])
    text = node_text(node)
    return text.strip("().")


def _callee_identifiers(node: Any) -> list[Any]:
    identifiers: list[Any] = []
    for candidate in walk(node):
        if candidate.type not in {"identifier", "type_identifier"}:
            continue
        ancestor = candidate.parent
        is_argument = False
        while ancestor is not None and ancestor != node:
            if ancestor.type in {"argument", "arguments", "argument_part"}:
                is_argument = True
                break
            ancestor = ancestor.parent
        if not is_argument:
            identifiers.append(candidate)
    return identifiers


def _contains_anonymous_function(node: Any) -> bool:
    return any(candidate.type == "function_expression" for candidate in walk(node))


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
