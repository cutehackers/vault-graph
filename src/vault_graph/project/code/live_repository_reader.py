"""Read one git repository directly, without registration or a code projection.

``explore_project`` uses this reader when the folder it is given lies in a git repository
that is not registered (spec 2026-11-25-explore-project-cwd-git-2 D3-D5). The reader lists
files through git, picks candidate files with ``git grep`` for words of the task, parses only
those Python and Dart files in memory, and returns symbol and line hits. It only runs
``git rev-parse``, ``git ls-files`` and ``git grep`` with ``GIT_OPTIONAL_LOCKS=0``, so it
never rewrites the git index, and it keeps nothing after the call (I1). Each call has
fixed limits on terms, git time, parsed files and file size (I7).
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from vault_graph.project.code.code_models import CODE_PARSER_SPEC_VERSION, CodeFileInput
from vault_graph.project.code.dart_parser import DartCodeParserAdapter
from vault_graph.project.code.parser_adapter import CodeParserAdapter
from vault_graph.project.code.python_parser import PythonCodeParserAdapter
from vault_graph.project.code.source_scanning import DEFAULT_EXCLUDED_DIRECTORIES

MAX_TERMS = 8
GIT_COMMAND_TIMEOUT_S = 5.0
GIT_TOTAL_TIMEOUT_S = 10.0
MAX_PARSED_FILES = 50
MAX_FILE_BYTES = 512 * 1024

_SYMLINK_MODE = "120000"
_SUBMODULE_MODE = "160000"
_LANGUAGES = {".py": "python", ".dart": "dart"}
_ASCII_TERM = re.compile(r"[A-Za-z0-9_]{3,}")
_HANGUL_TERM = re.compile(r"[가-힣]{2,}")
_STOP_WORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "into",
        "how",
        "what",
        "why",
        "when",
        "where",
        "which",
        "are",
        "was",
        "were",
        "has",
        "have",
        "not",
        "but",
        "all",
        "any",
        "can",
        "should",
        "would",
        "does",
        "use",
        "using",
    }
)

HitKind = Literal["symbol", "line"]


@dataclass(frozen=True)
class GitResult:
    """One git run. ``returncode`` is None when git could not start or timed out."""

    returncode: int | None
    stdout: str
    timed_out: bool = False


GitRunner = Callable[[Path, tuple[str, ...], float], GitResult]


@dataclass(frozen=True)
class LiveRepository:
    """A git repository found from a folder.

    ``root_path`` is the working tree that is read. ``label`` names the main worktree folder so
    every worktree of one repository shares it. ``head`` is None before the first commit.
    """

    root_path: Path
    label: str
    head: str | None


class RepositoryLike(Protocol):
    """What ``search`` reads from a repository; ``LiveRepository`` is one."""

    @property
    def root_path(self) -> Path: ...

    @property
    def label(self) -> str: ...

    @property
    def head(self) -> str | None: ...


@dataclass(frozen=True)
class LiveCodeHit:
    kind: HitKind
    relative_path: str
    start_line: int
    end_line: int
    title: str
    summary: str
    matched_terms: int
    symbol_id: str | None = None


@dataclass(frozen=True)
class LiveCodeSearch:
    hits: tuple[LiveCodeHit, ...]
    warnings: tuple[str, ...]
    truncated: bool
    files_parsed: int


def extract_terms(task: str) -> tuple[str, ...]:
    """Lowercased words of the task in order: ASCII runs of 3+, Hangul runs of 2+, at most eight."""

    found: list[tuple[int, str]] = [(match.start(), match.group()) for match in _ASCII_TERM.finditer(task)]
    found += [(match.start(), match.group()) for match in _HANGUL_TERM.finditer(task)]
    terms: list[str] = []
    for _, raw in sorted(found):
        term = raw.casefold()
        if term in _STOP_WORDS or term in terms:
            continue
        terms.append(term)
        if len(terms) == MAX_TERMS:
            break
    return tuple(terms)


def run_git_command(folder: Path, arguments: tuple[str, ...], timeout_s: float) -> GitResult:
    """Run git without optional locks so a read never rewrites the index."""

    environment = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    try:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=folder,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return GitResult(returncode=None, stdout="", timed_out=True)
    except (OSError, subprocess.SubprocessError):
        return GitResult(returncode=None, stdout="")
    return GitResult(returncode=completed.returncode, stdout=completed.stdout)


class _GitBudget:
    def __init__(self, runner: GitRunner, root: Path) -> None:
        self._runner = runner
        self._root = root
        self._deadline = time.monotonic() + GIT_TOTAL_TIMEOUT_S
        self.exhausted = False

    def run(self, *arguments: str) -> GitResult | None:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            self.exhausted = True
            return None
        result = self._runner(self._root, arguments, min(GIT_COMMAND_TIMEOUT_S, remaining))
        if result.timed_out:
            self.exhausted = True
        return result


class LiveRepositoryReader:
    """Find the git repository of a folder and search it for a task without writing anything."""

    def __init__(
        self,
        *,
        runner: GitRunner | None = None,
        parsers: Mapping[str, CodeParserAdapter] | None = None,
    ) -> None:
        self._runner: GitRunner = runner or run_git_command
        self._parsers: dict[str, CodeParserAdapter] = dict(
            parsers or {"python": PythonCodeParserAdapter(), "dart": DartCodeParserAdapter()}
        )

    def run(self, folder: Path, arguments: tuple[str, ...], timeout_s: float) -> GitResult:
        return self._runner(folder, arguments, timeout_s)

    def git_available(self) -> bool:
        result = self._runner(Path.cwd(), ("--version",), GIT_COMMAND_TIMEOUT_S)
        return result.returncode == 0

    def find_repository(self, path: Path) -> LiveRepository | None:
        try:
            folder = path.expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        if not folder.is_dir():
            folder = folder.parent
        top = self._output(folder, "rev-parse", "--show-toplevel")
        if not top:
            return None
        root = Path(top).resolve()
        common = self._output(folder, "rev-parse", "--path-format=absolute", "--git-common-dir")
        main_root = root
        if common:
            common_path = Path(common)
            if common_path.name == ".git":
                main_root = common_path.parent
        head = self._output(root, "rev-parse", "--verify", "--quiet", "HEAD")
        return LiveRepository(root_path=root, label=f"git:{main_root.name}", head=head or None)

    def search(self, repository: RepositoryLike, task: str, *, limit: int) -> LiveCodeSearch:
        terms = extract_terms(task)
        if not terms:
            return LiveCodeSearch(hits=(), warnings=("code_live_no_terms",), truncated=False, files_parsed=0)
        budget = _GitBudget(self._runner, repository.root_path)
        listed = self._list_files(budget)
        if listed is None:
            return LiveCodeSearch(hits=(), warnings=("code_live_read_truncated",), truncated=True, files_parsed=0)
        readable, skipped = listed
        matches: dict[str, set[str]] = {}
        for path in readable:
            lowered = path.casefold()
            for term in terms:
                if term in lowered:
                    matches.setdefault(path, set()).add(term)
        for term in terms:
            result = budget.run("grep", "-l", "-z", "-i", "-F", "-I", "--untracked", "-e", term)
            if result is None or result.timed_out:
                break
            if result.returncode not in (0, 1):
                continue
            for path in result.stdout.split("\0"):
                if path in readable:
                    matches.setdefault(path, set()).add(term)
        truncated = budget.exhausted
        ranked = sorted(matches, key=lambda path: (-len(matches[path]), path))
        if len(ranked) > MAX_PARSED_FILES:
            ranked = ranked[:MAX_PARSED_FILES]
            truncated = True
        symbol_hits: list[LiveCodeHit] = []
        line_hits: list[LiveCodeHit] = []
        files_parsed = 0
        for relative in ranked:
            content = _read_file(repository.root_path, relative)
            if content is None:
                skipped += 1
                continue
            language = _LANGUAGES.get(PurePosixPath(relative).suffix.casefold())
            symbols: list[LiveCodeHit] | None = None
            if language is not None and language in self._parsers:
                files_parsed += 1
                symbols = self._symbol_hits(repository, relative, language, content, terms)
            if symbols:
                symbol_hits.extend(symbols)
                continue
            line_hit = _line_hit(relative, content, terms)
            if line_hit is not None:
                line_hits.append(line_hit)
        hits = tuple(
            sorted(symbol_hits, key=lambda hit: (-hit.matched_terms, hit.relative_path, hit.start_line))
            + sorted(line_hits, key=lambda hit: (-hit.matched_terms, hit.relative_path, hit.start_line))
        )[: max(0, limit)]
        warnings: list[str] = []
        if skipped:
            warnings.append("code_live_files_skipped")
        if truncated:
            warnings.append("code_live_read_truncated")
        if not hits and not truncated:
            warnings.append("code_live_no_match")
        return LiveCodeSearch(hits=hits, warnings=tuple(warnings), truncated=truncated, files_parsed=files_parsed)

    def _output(self, folder: Path, *arguments: str) -> str | None:
        result = self._runner(folder, arguments, GIT_COMMAND_TIMEOUT_S)
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    @staticmethod
    def _list_files(budget: _GitBudget) -> tuple[set[str], int] | None:
        result = budget.run("ls-files", "-s", "-z", "--cached", "--others", "--exclude-standard")
        if result is None or result.returncode != 0:
            return None
        readable: set[str] = set()
        skipped = 0
        for entry in result.stdout.split("\0"):
            if not entry:
                continue
            mode, _, path = _split_ls_entry(entry)
            if mode in (_SYMLINK_MODE, _SUBMODULE_MODE):
                skipped += 1
                continue
            parts = PurePosixPath(path).parts
            if set(parts[:-1]) & DEFAULT_EXCLUDED_DIRECTORIES:
                continue
            readable.add(path)
        return readable, skipped

    def _symbol_hits(
        self,
        repository: RepositoryLike,
        relative: str,
        language: str,
        content: bytes,
        terms: tuple[str, ...],
    ) -> list[LiveCodeHit] | None:
        parser = self._parsers[language]
        try:
            parsed = parser.parse(
                CodeFileInput(
                    repository_id=repository.label,
                    relative_path=relative,
                    language=language,
                    content=content,
                    content_hash=hashlib.sha256(content).hexdigest(),
                    source_revision=f"git:{repository.head}" if repository.head else "git:working-tree",
                    is_test_file=_is_test_path(relative),
                    parser_spec_version=getattr(parser, "parser_spec_version", CODE_PARSER_SPEC_VERSION),
                )
            )
        except Exception:  # noqa: BLE001 - a file the parser cannot read falls back to a line hit (F7).
            return None
        if any(item.severity == "error" for item in parsed.diagnostics):
            return None
        hits: list[LiveCodeHit] = []
        for symbol in parsed.symbols:
            name = symbol.name.casefold()
            matched = sum(1 for term in terms if term in name)
            if not matched:
                continue
            hits.append(
                LiveCodeHit(
                    kind="symbol",
                    relative_path=relative,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    title=symbol.qualified_name,
                    summary=symbol.signature or symbol.kind,
                    matched_terms=matched,
                    symbol_id=symbol.symbol_id,
                )
            )
        return hits


def _split_ls_entry(entry: str) -> tuple[str, str, str]:
    """``<mode> <object> <stage>\\t<path>`` for index entries, a bare path for untracked files."""

    meta, tab, path = entry.partition("\t")
    if not tab:
        return "", "", entry
    return meta.split(" ", 1)[0], "", path


def _read_file(root: Path, relative: str) -> bytes | None:
    path = root / relative
    try:
        info = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
        return None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        with os.fdopen(descriptor, "rb") as handle:
            content = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    if len(content) > MAX_FILE_BYTES:
        return None
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return content


def _line_hit(relative: str, content: bytes, terms: tuple[str, ...]) -> LiveCodeHit | None:
    text = content.decode("utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        lowered = line.casefold()
        matched = [term for term in terms if term in lowered]
        if matched:
            return LiveCodeHit(
                kind="line",
                relative_path=relative,
                start_line=number,
                end_line=number,
                title=relative,
                summary=f"line match: {matched[0]}",
                matched_terms=len(matched),
            )
    return None


def _is_test_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    name = path.name.casefold()
    return bool(
        {part.casefold() for part in path.parts[:-1]} & {"test", "tests"}
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith("_test.dart")
    )


__all__ = [
    "GitResult",
    "GitRunner",
    "LiveCodeHit",
    "LiveCodeSearch",
    "LiveRepository",
    "LiveRepositoryReader",
    "extract_terms",
    "run_git_command",
]
