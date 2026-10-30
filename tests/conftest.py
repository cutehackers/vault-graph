from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_vault_map(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep tests off the machine's real $HOME/.claude/vault-builder/vault-map.json.
    missing = tmp_path_factory.mktemp("no-vault-map") / "vault-map.json"
    monkeypatch.setenv("VAULT_GRAPH_VAULT_MAP", str(missing))


@pytest.fixture
def vault_with_page(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    return vault_root
