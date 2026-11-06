"""Enforce the import direction between functional areas M01-M19.

Source: modularization remediation plan, 보완1 (발견10), and VG-MOD-20261015 §4 DEP-01..07.
The transport and composition ban for feature code stays in test_functional_module_boundaries.py.
Storage layers are import targets here, not checked sources.
"""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).parents[1] / "src" / "vault_graph"

# Area table. A key ending in "/" is a package prefix, any other key is one module file.
# The longest matching key wins. Paths are relative to src/vault_graph.
_AREAS: dict[str, str] = {
    "operation/scope/": "M01",  # vault_scope
    "indexing/ingestion/": "M02",  # document_ingestion
    "indexing/": "M03",  # projection_indexing (includes indexing/extraction)
    "indexing/publication/": "M04",  # projection_publication
    "retrieval/search/": "M05",  # hybrid_retrieval
    "retrieval/graph/": "M06",  # graph_retrieval
    "retrieval/evidence/": "M07",  # evidence_linking
    "context/pack/": "M08",  # context_pack
    "context/answer/": "M09",  # extractive_answer
    "context/memory/": "M10",  # memory_views
    "project/code/": "M11",  # code_projection
    "project/context/": "M12",  # project_context
    "retrieval/explanation/": "M13",  # result_explanation
    "operation/readiness/": "M14",  # projection_readiness
    "operation/diagnostics/": "M15",  # projection_diagnostics
    "operation/runtime/": "M16",  # runtime_operations
    "operation/integration/": "M17",  # integration_configuration
    "operation/memory/": "M18",  # memory_write
    "operation/sessions/": "M19",  # session_normalization (spec 2026-11-05 §4.2.2)
    "storage/interfaces/": "PORT",  # read/write ports, importable by every area
    "storage/local/": "STORE",  # concrete storage, built only by composition
    "interface/": "COMPOSITION",  # transports and composition, see test_functional_module_boundaries.py
    "errors.py": "SUPPORT",
    # Local-Graph phase 1 modules (spec 2026-10-29 §4.2.2-4.2.4). Listed before they exist.
    "operation/integration/vault_map.py": "M17",
    "interface/composition/adapters/vault_publish_cli.py": "COMPOSITION",
    "context/pack/recall.py": "M08",
    "storage/local/usage_log.py": "STORE",
    # Vault long-term memory modules (spec 2026-11-02 V1). Listed before they exist.
    "operation/memory/memory_requests.py": "M18",
    "operation/memory/memory_target.py": "M18",
    "operation/memory/memory_drafts.py": "M18",
    "operation/memory/memory_ports.py": "M18",
    "operation/memory/memory_write_service.py": "M18",
    "context/pack/recall_pins.py": "M08",
    "interface/composition/vault_labels.py": "COMPOSITION",
    "interface/composition/adapters/vault_page_reader.py": "COMPOSITION",
    "interface/composition/adapters/vault_capture_cli.py": "COMPOSITION",
}

_PLANNED_MODULES = (
    "operation/integration/vault_map.py",
    "interface/composition/adapters/vault_publish_cli.py",
    "context/pack/recall.py",
    "storage/local/usage_log.py",
    "operation/memory/memory_requests.py",
    "operation/memory/memory_target.py",
    "operation/memory/memory_drafts.py",
    "operation/memory/memory_ports.py",
    "operation/memory/memory_write_service.py",
    "context/pack/recall_pins.py",
    "interface/composition/vault_labels.py",
    "interface/composition/adapters/vault_page_reader.py",
    "interface/composition/adapters/vault_capture_cli.py",
)

# Areas every feature may import, besides its own area.
_SHARED_AREAS = frozenset({"PORT", "SUPPORT"})

# Owner-local contract modules any feature may import (remediation plan §2, VG-MOD §4
# "포트와 DTO는 소유 기능 가까이 둔다"). graph_projection holds the projection DTOs and
# Protocol that M03 builds for graph indexing.
_CONTRACT_MODULES = frozenset(
    {
        "vault_graph.retrieval.graph.graph_contracts",
        "vault_graph.retrieval.graph.graph_identity",
        "vault_graph.retrieval.graph.graph_readiness",
        "vault_graph.retrieval.graph.projection.graph_projection",
        "vault_graph.project.code.code_models",
    }
)

# Allowed direction: source area -> other feature areas it may import.
# Follows the VG-MOD §4 flow: QUERY(M09, M12) -> VIEW(M08, M10) -> RET(M05, M06) -> LINK(M07), READY(M14),
# OPS(M16, M17) -> IDX(M02, M03), PUB(M04), and M01 as the lowest area.
_ALLOWED: dict[str, frozenset[str]] = {
    "M01": frozenset(),  # DEP-01
    "M02": frozenset({"M01"}),
    "M03": frozenset({"M01", "M02"}),  # DEP-06: no M04
    "M04": frozenset({"M01"}),
    "M05": frozenset({"M01", "M02", "M07", "M14"}),
    # M06 implements the M05 GraphCandidateProvider port and returns M05 DTOs. 발견8-b is cut on the M05 side.
    "M06": frozenset({"M01", "M02", "M05", "M07"}),
    "M07": frozenset({"M01"}),  # DEP-05: read ports and graph contracts only
    # M08 -> M10: recall reuses STALE_STATUSES from context/memory/project_memory.py (spec §4.2.3).
    "M08": frozenset({"M01", "M02", "M05", "M06", "M07", "M10", "M14"}),
    "M09": frozenset({"M01", "M02", "M05", "M06", "M07", "M08", "M10", "M14"}),  # DEP-04
    "M10": frozenset({"M01", "M02", "M05", "M06", "M07", "M14"}),  # DEP-02: no M15
    "M11": frozenset({"M01"}),
    "M12": frozenset({"M01", "M02", "M05", "M06", "M07", "M08", "M11", "M14"}),  # DEP-01, DEP-04: no M17
    "M13": frozenset({"M01"}),
    "M14": frozenset({"M01"}),  # DEP-02
    "M15": frozenset({"M01", "M02", "M03", "M06", "M10", "M14"}),  # DEP-02: M15 reads feature status
    "M16": frozenset({"M01", "M02", "M03", "M04", "M17"}),
    "M17": frozenset({"M01", "M12"}),  # 보완5: M17 implements the M12 binding read Protocol
    # 결정S1: Vault memory writes read the M12 VaultMapReader and MappedVault. Only composition builds M18.
    "M18": frozenset({"M01", "M12"}),
    # 결정18: session adapters are pure code over M01. Only composition reads files and calls them.
    "M19": frozenset({"M01"}),
}

# Current violations, fixed per (source file, imported module). Remove an entry when its fix lands.
# Do not add entries. A new violation must be fixed or recorded as a VG-MOD rule exception (결정2).
_KNOWN_VIOLATIONS: frozenset[tuple[str, str]] = frozenset()
_KNOWN_VIOLATION_CEILING = 0

_DYNAMIC_MODULE = re.compile(r"vault_graph(\.\w+)+")


def _module_file(module: str) -> Path | None:
    parts = module.split(".")[1:]
    if not parts:
        return SRC / "__init__.py"
    candidate = SRC.joinpath(*parts)
    if candidate.with_suffix(".py").is_file():
        return candidate.with_suffix(".py")
    if (candidate / "__init__.py").is_file():
        return candidate / "__init__.py"
    return None


def _module_path(module: str) -> str:
    path = _module_file(module)
    if path is not None:
        return path.relative_to(SRC).as_posix()
    return "/".join(module.split(".")[1:]) + ".py"


def _area_of_path(path: str) -> str | None:
    matches = [key for key in _AREAS if path == key or (key.endswith("/") and path.startswith(key))]
    return _AREAS[max(matches, key=len)] if matches else None


def collect_imports(source: str, module: str, *, is_package: bool) -> set[str]:
    """Return every vault_graph module the source imports.

    ast.walk visits module-level, function-local (lazy) and ``if TYPE_CHECKING`` imports alike.
    String module names count as imports when the file calls ``import_module``.
    """
    tree = ast.parse(source)
    package = module.split(".") if is_package else module.split(".")[:-1]
    found: set[str] = set()
    uses_import_module = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "importlib" and any(alias.name == "import_module" for alias in node.names):
                uses_import_module = True
            if node.level:
                base = package[: len(package) - node.level + 1]
                parent = ".".join([*base, node.module] if node.module else base)
            else:
                parent = node.module or ""
            for alias in node.names:
                submodule = f"{parent}.{alias.name}"
                found.add(submodule if _module_file(submodule) is not None else parent)
        elif isinstance(node, ast.Name) and node.id == "import_module":
            uses_import_module = True
        elif isinstance(node, ast.Attribute) and node.attr == "import_module":
            uses_import_module = True
    if uses_import_module:
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _DYNAMIC_MODULE.fullmatch(node.value):
                found.add(node.value)
    return {name for name in found if name == "vault_graph" or name.startswith("vault_graph.")}


def _is_allowed(source_area: str, target: str) -> bool:
    target_area = _area_of_path(_module_path(target))
    if target_area is None:
        # Unknown path or package root: feature code must import the canonical module.
        return False
    return (
        target_area == source_area
        or target_area == "COMPOSITION"
        or target_area in _SHARED_AREAS
        or target in _CONTRACT_MODULES
        or target_area in _ALLOWED[source_area]
    )


def feature_violations() -> set[tuple[str, str]]:
    violations: set[tuple[str, str]] = set()
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        area = _area_of_path(relative)
        if area is None or area not in _ALLOWED:
            continue
        is_package = path.name == "__init__.py"
        parts = path.relative_to(SRC.parent).with_suffix("").parts
        module = ".".join(parts[:-1] if is_package else parts)
        for target in collect_imports(path.read_text(encoding="utf-8"), module, is_package=is_package):
            if not _is_allowed(area, target):
                violations.add((relative, target))
    return violations


def test_area_table_points_at_existing_packages() -> None:
    for key in _AREAS:
        if key.endswith("/"):
            assert (SRC / key).is_dir(), key
        elif key in _PLANNED_MODULES:
            assert (SRC / key).parent.is_dir(), key
        else:
            assert (SRC / key).is_file(), key


@pytest.mark.parametrize("path", _PLANNED_MODULES)
def test_local_graph_modules_are_in_area_table(path: str) -> None:
    assert path in _AREAS
    assert _area_of_path(path) == _AREAS[path]


def test_allowed_direction_table_has_no_cycle() -> None:
    def reaches(start: str, goal: str, seen: set[str]) -> bool:
        for nxt in _ALLOWED[start]:
            if nxt == goal or (nxt not in seen and reaches(nxt, goal, seen | {nxt})):
                return True
        return False

    assert [area for area in _ALLOWED if reaches(area, area, set())] == []


def test_collector_sees_lazy_type_checking_relative_and_dynamic_imports() -> None:
    source = """
from typing import TYPE_CHECKING
from importlib import import_module

if TYPE_CHECKING:
    from vault_graph.operation.diagnostics.index_status_reader import StatusReport

from .context_pack import ContextPack


def lazy() -> None:
    from vault_graph.storage.local import sqlite_metadata_store
    import vault_graph.retrieval.search.search_response

_EXPORTS = {"X": ("vault_graph.operation.integration.project_binding_catalog", "X")}
"""
    assert collect_imports(source, "vault_graph.context.pack.example", is_package=False) == {
        "vault_graph.operation.diagnostics.index_status_reader",
        "vault_graph.context.pack.context_pack",
        "vault_graph.storage.local.sqlite_metadata_store",
        "vault_graph.retrieval.search.search_response",
        "vault_graph.operation.integration.project_binding_catalog",
    }


@pytest.mark.parametrize(
    ("source_area", "target", "allowed"),
    [
        ("M10", "vault_graph.operation.diagnostics.index_status_reader", False),  # DEP-02
        ("M08", "vault_graph.storage.local.usage_log", False),  # recall gets the usage log as a port
        ("M08", "vault_graph.operation.integration.vault_map", False),  # recall gets the vault map injected
        ("M12", "vault_graph.operation.integration.vault_map", False),  # DEP-01
        ("M17", "vault_graph.storage.local.usage_log", False),
        ("M05", "vault_graph.retrieval.retrieval_service", False),  # removed previous path
        ("M08", "vault_graph.context.memory.project_memory", True),
        ("M07", "vault_graph.retrieval.graph.graph_contracts", True),
        ("M07", "vault_graph.retrieval.graph.graph_retrieval_service", False),
        ("M17", "vault_graph.storage.interfaces.metadata_store", True),
        ("M18", "vault_graph.project.context.project_binding_reader", True),
        ("M18", "vault_graph.operation.integration.vault_map", False),  # the vault map is injected
        ("M17", "vault_graph.operation.memory.memory_requests", False),  # only composition builds M18
        ("M10", "vault_graph.operation.memory.memory_requests", False),
        ("M19", "vault_graph.operation.scope.path_guard", True),
        ("M19", "vault_graph.operation.memory.memory_requests", False),
        ("M17", "vault_graph.operation.sessions.claude_code_adapter", False),  # only composition calls M19
    ],
)
def test_direction_rule_examples(source_area: str, target: str, allowed: bool) -> None:
    assert _is_allowed(source_area, target) is allowed


def test_no_area_imports_memory_write() -> None:
    assert sorted(area for area, targets in _ALLOWED.items() if "M18" in targets) == []


def test_no_area_imports_session_normalization() -> None:
    assert sorted(area for area, targets in _ALLOWED.items() if "M19" in targets) == []


def test_feature_imports_follow_direction_table() -> None:
    new = sorted(feature_violations() - _KNOWN_VIOLATIONS)
    assert new == [], "feature import breaks the direction table; inject a port instead"


def test_known_violation_list_only_shrinks() -> None:
    assert len(_KNOWN_VIOLATIONS) <= _KNOWN_VIOLATION_CEILING
    stale = sorted(_KNOWN_VIOLATIONS - feature_violations())
    assert stale == [], "fixed violation is still listed; remove it and lower the ceiling"
