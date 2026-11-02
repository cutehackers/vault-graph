from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_functional_module_boundaries import assert_policy_imports
from tests.test_setup_service import RecordingIndexFactory, make_vault
from vault_graph.operation.runtime.setup_service import SetupRequest, SetupService
from vault_graph.operation.runtime.watch_service import WatchService
from vault_graph.operation.scope.vault_catalog import QueryScope


@pytest.mark.parametrize("package", ("operation/runtime", "operation/integration"))
def test_operations_do_not_import_composition_transport_or_local_storage(package: str) -> None:
    root = Path(__file__).parents[1] / "src" / "vault_graph" / package
    assert_policy_imports(root, forbidden=("vault_graph.storage.local",))


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
        original_run_apply = factory.index_service.run_apply

        def run_apply_with_change(**kwargs: object) -> object:
            # Watch publishes only when files changed, so the publication path needs a change.
            report = original_run_apply(**kwargs)
            return replace(report, metadata=replace(report.metadata, changed_paths=(("main", "wiki/page.md"),)))

        monkeypatch.setattr(factory.index_service, "run_apply", run_apply_with_change)

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
