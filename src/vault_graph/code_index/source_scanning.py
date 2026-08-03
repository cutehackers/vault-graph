"""Read-only source repository scanning and deterministic file fingerprints."""

from __future__ import annotations

import fnmatch
import hashlib
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from vault_graph.code_index.code_models import CODE_PARSER_SPEC_VERSION, CodeFileInput, CodeRepositoryEntry
from vault_graph.code_index.repository_catalog import repository_policy_revision

DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".bzr",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "vendor",
        "build",
        "dist",
        "out",
        "coverage",
        "generated",
        ".dart_tool",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)


class CodeSourceScanError(ValueError):
    """Raised when a repository cannot be scanned safely."""


@dataclass(frozen=True)
class CodeScanResult:
    repository_id: str
    files: tuple[CodeFileInput, ...]
    source_revision: str
    policy_revision: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.repository_id.strip():
            raise ValueError("repository_id is required")
        if not isinstance(self.files, tuple):
            raise ValueError("files must be a tuple")
        if not self.source_revision.strip() or not self.policy_revision.strip():
            raise ValueError("scan revisions are required")
        if not isinstance(self.warnings, tuple):
            raise ValueError("warnings must be a tuple")


class CodeSourceScanner:
    """Scan one registered repository without mutating its files or metadata."""

    def __init__(self, *, parser_spec_version: str = CODE_PARSER_SPEC_VERSION) -> None:
        if not parser_spec_version.strip():
            raise ValueError("parser_spec_version is required")
        self.parser_spec_version = parser_spec_version

    def scan(self, repository: CodeRepositoryEntry) -> CodeScanResult:
        if not isinstance(repository, CodeRepositoryEntry):
            raise TypeError("repository must be a CodeRepositoryEntry")
        root = repository.root_path.expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise CodeSourceScanError(f"repository root is unavailable: {root}")
        selected: list[tuple[str, bytes, str, bool]] = []
        warnings: list[str] = []
        for path in sorted(_walk_files(root), key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                resolved = path.resolve(strict=False)
                if resolved != root and root not in resolved.parents:
                    raise CodeSourceScanError(f"source symlink escapes repository root: {relative} -> {resolved}")
                if resolved.is_dir():
                    continue
            if not _is_selected(relative, repository):
                continue
            language = _language_for_path(relative)
            if language is None or language not in repository.languages:
                continue
            try:
                content = path.read_bytes()
            except (OSError, PermissionError) as exc:
                warnings.append(f"source_unavailable:{relative}:{exc}")
                continue
            selected.append((relative, content, language, _is_test_path(relative)))

        selected.sort(key=lambda item: item[0])
        source_revision = _source_revision(root, selected)
        files = tuple(
            CodeFileInput(
                repository_id=repository.repository_id,
                relative_path=relative,
                language=language,
                content=content,
                content_hash=hashlib.sha256(content).hexdigest(),
                source_revision=source_revision,
                is_test_file=is_test,
                parser_spec_version=self.parser_spec_version,
            )
            for relative, content, language, is_test in selected
        )
        return CodeScanResult(
            repository_id=repository.repository_id,
            files=files,
            source_revision=source_revision,
            policy_revision=repository_policy_revision(repository),
            warnings=tuple(sorted(set(warnings))),
        )


# Short aliases keep adapters independent of the implementation name.
SourceScanner = CodeSourceScanner
ScanResult = CodeScanResult


def scan_repository(
    repository: CodeRepositoryEntry,
    *,
    parser_spec_version: str = CODE_PARSER_SPEC_VERSION,
) -> CodeScanResult:
    return CodeSourceScanner(parser_spec_version=parser_spec_version).scan(repository)


def _walk_files(root: Path) -> Iterable[Path]:
    # ``Path.rglob`` does not recurse through symlinked directories on the
    # supported Python versions. We still inspect symlinked files so an
    # internal alias is safe and an external alias is rejected above.
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            continue
        if path.is_file() or path.is_symlink():
            yield path


def _is_selected(relative: str, repository: CodeRepositoryEntry) -> bool:
    path = PurePosixPath(relative)
    parts = set(path.parts[:-1])
    default_excluded = bool(parts & DEFAULT_EXCLUDED_DIRECTORIES)
    explicit_include = any(_matches(relative, pattern) for pattern in repository.include_globs)
    if any(_matches(relative, pattern) for pattern in repository.exclude_globs):
        return False
    if repository.include_globs and not explicit_include:
        return False
    return not default_excluded or explicit_include


def _matches(relative: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/").lstrip("./")
    if PurePosixPath(relative).match(normalized) or fnmatch.fnmatchcase(relative, normalized):
        return True
    if normalized.startswith("**/") and fnmatch.fnmatchcase(relative, normalized[3:]):
        return True
    if normalized.endswith("/**"):
        prefix = normalized[:-3].rstrip("/")
        return relative == prefix or relative.startswith(prefix + "/")
    return False


def _language_for_path(relative: str) -> str | None:
    suffix = Path(relative).suffix.casefold()
    return {".py": "python", ".dart": "dart"}.get(suffix)


def _is_test_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    name = path.name.casefold()
    return bool(
        {part.casefold() for part in path.parts[:-1]} & {"test", "tests"}
        or name.startswith("test_")
        or name.startswith("test.")
        or name.endswith("_test.py")
        or name.endswith("_test.dart")
    )


def _source_revision(root: Path, selected: list[tuple[str, bytes, str, bool]]) -> str:
    content_digest = _selected_digest(selected)
    head = _git(root, "rev-parse", "HEAD")
    if head is None:
        return f"content-hash:{content_digest}"
    dirty = _git(root, "status", "--porcelain", "--untracked-files=all")
    if dirty is None:
        return f"git:{head}"
    if dirty:
        dirty_digest = hashlib.sha256((dirty + "\n" + content_digest).encode("utf-8")).hexdigest()
        return f"git:{head}+wt:{dirty_digest}"
    return f"git:{head}"


def _selected_digest(selected: list[tuple[str, bytes, str, bool]]) -> str:
    digest = hashlib.sha256()
    for relative, content, language, is_test in selected:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(language.encode("utf-8"))
        digest.update(b"\0")
        digest.update(b"1" if is_test else b"0")
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def _git(root: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ("git", *arguments),
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()
