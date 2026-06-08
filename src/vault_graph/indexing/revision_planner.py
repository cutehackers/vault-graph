from dataclasses import dataclass


@dataclass(frozen=True)
class MetadataRevisionPlan:
    index_revision: str
    mode: str
    vault_ids: tuple[str, ...]
    changed_paths: tuple[tuple[str, str], ...]
    unchanged_paths: tuple[tuple[str, str], ...]
    deleted_paths: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]
