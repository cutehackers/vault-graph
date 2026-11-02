"""``VaultPageReader`` that reads one Vault page from disk and never writes (spec 2026-11-02 V1).

The update path reads the current page to keep its frontmatter and rechecks the page sha256 right
before publish (결정S8). A path that leaves the Vault root, including through a symbolic link, reads
as no page.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from vault_graph.operation.memory.memory_ports import PageText


class VaultPageFileReader:
    def read(self, vault_root: Path, path: str) -> PageText | None:
        root = vault_root.resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return None
        try:
            data = target.read_bytes()
        except OSError:
            return None
        # A page that is not UTF-8 still exists. The hash comes from the bytes, so a recheck stays exact.
        return PageText(text=data.decode("utf-8", errors="replace"), sha256=hashlib.sha256(data).hexdigest())


__all__ = ["VaultPageFileReader"]
