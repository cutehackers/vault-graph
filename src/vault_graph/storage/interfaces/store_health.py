from dataclasses import dataclass


@dataclass(frozen=True)
class StoreHealth:
    ok: bool
    backend: str
    schema_version: str
    schema_compatible: bool
    message: str
