from __future__ import annotations

from pathlib import Path


def test_readme_promotes_setup_as_first_run_path() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    install_index = readme.index("## Install")
    quick_start_index = readme.index("## Quick Start")
    common_commands_index = readme.index("## Common Commands")

    quick_start = readme[quick_start_index:common_commands_index]

    assert install_index < quick_start_index
    assert "uv tool install vault-graph" in readme[install_index:quick_start_index]
    assert "vg setup --vault /path/to/llm-wiki --agent codex" in quick_start
    assert 'vg ask --state ~/.vault-graph "What changed recently?"' in quick_start
    assert 'vg search --state ~/.vault-graph "GraphRAG"' in quick_start
    assert 'vg context --state ~/.vault-graph "Implement GraphRAG MVP"' in quick_start
    assert "vg status --state ~/.vault-graph" in quick_start
    normalized_quick_start = " ".join(quick_start.split())
    assert "first indexing run may download the pinned local embedding model" in normalized_quick_start.lower()


def test_readme_keeps_manual_init_and_mcp_details_out_of_first_path() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    quick_start = readme[readme.index("## Quick Start") : readme.index("## Common Commands")]

    assert "vg init" not in quick_start
    assert "implementation design" not in readme.lower()
    assert "Recommended Easy Setup" not in readme
