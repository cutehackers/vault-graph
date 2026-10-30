"""Module-level import cycles inside src/vault_graph stay at zero.

Source: modularization remediation plan, 보완7 (발견8-b, 8-c, 8-d).
test_feature_import_direction.py checks the direction between areas only, so a cycle between two
modules of the same package (for example document_authority <-> document_normalizer) needs this test.
Every import counts: module-level, function-local (lazy), ``if TYPE_CHECKING`` and ``import_module`` strings.
An import of ``a.b.c`` is an edge to ``a.b.c`` only, not to the parent package ``__init__`` modules.
"""

from tests.test_feature_import_direction import SRC, _module_file, collect_imports


def _import_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        is_package = path.name == "__init__.py"
        parts = path.relative_to(SRC.parent).with_suffix("").parts
        module = ".".join(parts[:-1] if is_package else parts)
        imports = collect_imports(path.read_text(encoding="utf-8"), module, is_package=is_package)
        graph[module] = {target for target in imports if target != module and _module_file(target) is not None}
    return graph


def import_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Return every strongly connected component with more than one module (Tarjan, iterative)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[list[str]] = []
    counter = 0
    for root in sorted(graph):
        if root in index:
            continue
        work: list[tuple[str, list[str]]] = [(root, sorted(graph[root]))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, pending = work[-1]
            if pending:
                target = pending.pop()
                if target not in graph:
                    continue
                if target not in index:
                    index[target] = low[target] = counter
                    counter += 1
                    stack.append(target)
                    on_stack.add(target)
                    work.append((target, sorted(graph[target])))
                elif target in on_stack:
                    low[node] = min(low[node], index[target])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    cycles.append(sorted(component))
    return sorted(cycles)


def test_cycle_finder_reports_two_and_three_module_cycles() -> None:
    graph = {
        "a": {"b"},
        "b": {"a"},
        "c": {"d"},
        "d": {"e"},
        "e": {"c", "f"},
        "f": set(),
    }
    assert import_cycles(graph) == [["a", "b"], ["c", "d", "e"]]


def test_source_has_no_module_import_cycle() -> None:
    assert import_cycles(_import_graph()) == [], "module import cycle; move the shared type to one side"
