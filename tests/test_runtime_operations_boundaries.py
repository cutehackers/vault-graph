from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_setup_service import RecordingIndexFactory, make_vault
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.runtime_operations.setup_service import SetupRequest, SetupService
from vault_graph.runtime_operations.watch_service import WatchService


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    (
        ("app.setup_service", "runtime_operations.setup_service"),
        ("app.watch_service", "runtime_operations.watch_service"),
        ("mcp.mcp_config_examples", "integration_configuration.mcp_config_examples"),
        ("mcp.mcp_config_registration", "integration_configuration.mcp_config_registration"),
    ),
)
def test_legacy_operation_modules_preserve_identity(legacy: str, canonical: str) -> None:
    assert importlib.import_module(f"vault_graph.{legacy}") is importlib.import_module(f"vault_graph.{canonical}")


@pytest.mark.parametrize("package", ("runtime_operations", "integration_configuration"))
def test_operations_do_not_import_composition_transport_or_local_storage(package: str) -> None:
    root = Path(__file__).parents[1] / "src" / "vault_graph" / package
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    for forbidden in (
        "vault_graph.app",
        "vault_graph.cli",
        "vault_graph.mcp",
        "vault_graph.http",
        "vault_graph.storage.local",
    ):
        assert forbidden not in source


@pytest.mark.parametrize("operation", ("setup", "watch"))
@pytest.mark.parametrize("failure", ("index", "publication", "interrupt"))
def test_operations_close_bundle_when_indexing_or_publication_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, failure: str
) -> None:
    factory = RecordingIndexFactory()
    if failure in ("index", "interrupt"):

        def fail_index(**kwargs: object) -> None:
            if failure == "interrupt":
                raise KeyboardInterrupt
            raise RuntimeError("index failed")

        monkeypatch.setattr(factory.index_service, "run_apply", fail_index)
    else:
        original_open = factory.open

        def open_with_publication_failure(**kwargs: object) -> object:
            bundle = original_open(**kwargs)

            def fail_publication(report: object) -> None:
                raise RuntimeError("publication failed")

            monkeypatch.setattr(bundle, "commit_projection", fail_publication, raising=False)
            return bundle

        monkeypatch.setattr(factory, "open", open_with_publication_failure)

    error = KeyboardInterrupt if failure == "interrupt" else RuntimeError
    with pytest.raises(error):
        if operation == "setup":
            SetupService(index_factory=cast(Any, factory)).setup(
                SetupRequest(vault_path=make_vault(tmp_path), graph_home_path=tmp_path / "state", vault_id="main")
            )
        else:
            WatchService(graph_home_path=tmp_path / "state", index_factory=cast(Any, factory)).run(
                scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
                interval_seconds=1,
                max_iterations=1,
            )

    assert len(factory.bundles) == 1
    assert factory.bundles[0].closed
