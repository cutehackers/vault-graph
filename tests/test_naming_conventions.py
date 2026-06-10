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
