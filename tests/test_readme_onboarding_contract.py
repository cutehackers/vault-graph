from __future__ import annotations

from pathlib import Path


def test_readme_promotes_setup_as_first_run_path() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    install_index = readme.index("## Install")
    quick_start_index = readme.index("## Quick Start")
    common_commands_index = readme.index("## Common Commands")

    quick_start = readme[quick_start_index:common_commands_index]

    assert install_index < quick_start_index
    install_section = readme[install_index:quick_start_index]
    assert "Status: Pre-release development" in readme
    first_install_block = install_section.split("```bash", 1)[1].split("```", 1)[0].strip()
    assert first_install_block == (
        "curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-builder/main/scripts/install.sh | bash"
    )
    normalized_install = " ".join(install_section.split())
    assert "404" not in normalized_install
    assert "--without-vault-graph" in install_section
    assert "uv tool install --python 3.12 git+https://github.com/cutehackers/vault-graph.git" in install_section
    assert "git+ssh" not in readme
    assert "me.github.com" not in readme
    assert "uv tool install vault-graph" not in readme
    assert "uv tool install --python 3.12 -e ." not in install_section
    assert "uv tool install --python 3.12 -e ." in readme[readme.index("## Develop From Source") :]
    first_setup = quick_start.split("```bash", 1)[1].split("```", 1)[0]
    assert "--agent claude" in first_setup.splitlines()[1]
    assert "vg setup --vault /path/to/vault --agent codex" in quick_start
    assert 'vg ask --graph-home ~/.vault-graph "What changed recently?"' in quick_start
    assert 'vg search --graph-home ~/.vault-graph "GraphRAG"' in quick_start
    assert 'vg context --graph-home ~/.vault-graph "Implement GraphRAG MVP"' in quick_start
    assert "vg status --graph-home ~/.vault-graph" in quick_start
    normalized_quick_start = " ".join(quick_start.split())
    assert "first indexing run may download the pinned local embedding model" in normalized_quick_start.lower()


def test_readme_keeps_manual_init_and_mcp_details_out_of_first_path() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    quick_start = readme[readme.index("## Quick Start") : readme.index("## Common Commands")]

    assert "vg init" not in quick_start
    assert "implementation design" not in readme.lower()
    assert "Recommended Easy Setup" not in readme


def _readme_section(readme: str, heading: str) -> str:
    start = readme.index(heading)
    next_heading = readme.find("\n## ", start + len(heading))
    return readme[start:] if next_heading == -1 else readme[start:next_heading]


def test_readme_explains_embedding_model_selection() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    section = _readme_section(readme, "## Embedding Model")
    normalized = " ".join(section.split()).lower()

    for text in ("e5-small", "~/llm/models", "vg embedding list", "vg embedding use", "EMBEDDING_PRESETS"):
        assert text in section
    assert "arctic-l" not in section
    assert "keyword results only until re-indexing finishes" in normalized


def test_readme_lists_embedding_commands_in_common_commands() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    common_commands = _readme_section(readme, "## Common Commands")

    assert "vg embedding list --graph-home ~/.vault-graph" in common_commands
    assert "vg embedding use e5-small --models-dir /path/to/models --graph-home ~/.vault-graph" in common_commands
