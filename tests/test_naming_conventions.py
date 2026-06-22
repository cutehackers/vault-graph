from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCANNED_PATHS = (
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / "docs",
)
IGNORED_FILES = {
    PROJECT_ROOT / "docs" / "CONVENTIONS.md",
}
FORBIDDEN_TERMS = (
    "effective" + "_",
    "effective " + "scope",
)


def test_forbidden_prefix_is_not_used_in_project_language() -> None:
    offenders: list[str] = []
    for base_path in SCANNED_PATHS:
        for path in sorted(base_path.rglob("*")):
            if path in IGNORED_FILES:
                continue
            if path.is_dir() or path.suffix not in {".md", ".py"}:
                continue
            text = path.read_text()
            lowered = text.lower()
            if any(term in lowered for term in FORBIDDEN_TERMS):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_forbidden_memory_store_paths_are_not_introduced() -> None:
    forbidden_path_parts = (
        "memory_store",
        "episode_log",
        "profile_memory",
        "preference_memory",
        "procedural_memory",
        "external_memory",
        "memory_server",
    )
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in (PROJECT_ROOT / "src" / "vault_graph").rglob("*")
        if any(part in path.as_posix().casefold() for part in forbidden_path_parts)
    ]

    assert offenders == []
    assert not (PROJECT_ROOT / "data" / "memory").exists()
