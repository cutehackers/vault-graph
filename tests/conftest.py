from pathlib import Path

import pytest


@pytest.fixture
def vault_with_page(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    return vault_root
