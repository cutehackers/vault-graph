"""``ExchangeTextReader`` that reads what the person typed in cited lines of a Vault session file (spec 2026-11-19 D4).

The memory write service uses it to check a quote against the session exchange the evidence names. It reads one
file under the Vault's `raw/sessions/` and never writes. A path outside that folder, or one that leaves the Vault
root through `..` or a symbolic link, reads as unreadable (None).

The person turns are found with the same rule the cleanup bundle uses (`memory_candidate_sources.exchange_human_text`),
so a quote that passes here also passes for the candidate of that exchange. The file format comes from the
frontmatter `schema` value: `vault-session/v2`, else the v1 rules.
"""

from __future__ import annotations

from pathlib import Path

from vault_graph.interface.composition.memory_candidate_sources import SESSION_PATH_PREFIX, exchange_human_text

_SCHEMA_V2 = "vault-session/v2"


class SessionExchangeFileReader:
    def human_text(self, vault_root: Path, path: str, line_start: int, line_end: int) -> str | None:
        if not path.startswith(SESSION_PATH_PREFIX):
            return None
        root = vault_root.resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return None
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return None
        if line_start < 1 or line_start > len(lines) or line_end < line_start:
            return None
        return exchange_human_text(lines[line_start - 1 : line_end], v2=_is_v2(lines))


def _is_v2(lines: list[str]) -> bool:
    """True when the frontmatter block says `schema: vault-session/v2`."""
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return False
        key, separator, value = line.partition(":")
        if separator and key.strip() == "schema":
            return value.strip().strip("\"'") == _SCHEMA_V2
    return False


__all__ = ["SessionExchangeFileReader"]
