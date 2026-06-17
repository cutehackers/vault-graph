from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, NoReturn
from urllib.parse import quote, unquote, urlsplit

from vault_graph.errors import CatalogError
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.mcp_errors import McpErrorPayload, McpProtocolError

McpResourceKind = Literal[
    "document",
    "page",
    "source",
    "concept",
    "decision",
    "issue",
    "timeline_recent",
    "context_current",
    "graph_entity",
    "context_pack",
]

_PATH_KINDS = {"document", "page"}


@dataclass(frozen=True)
class McpResourceUri:
    raw_uri: str
    normalized_uri: str
    kind: McpResourceKind
    vault_id: str | None
    value: str | None


def encode_resource_segment(value: str) -> str:
    return quote(value, safe="")


def decode_resource_segment(value: str, *, allow_slash: bool) -> str:
    decoded = unquote(value)
    _validate_decoded_value(decoded, allow_slash=allow_slash)
    return decoded


def parse_mcp_resource_uri(uri: str, *, catalog: VaultCatalog) -> McpResourceUri:
    parsed = urlsplit(uri)
    if parsed.scheme != "vault":
        _raise_invalid_resource_uri("resource URI must use vault:// scheme")
    if parsed.query or parsed.fragment:
        _raise_invalid_resource_uri("resource URI must not include query or fragment")

    path_parts = _path_parts(parsed.path)
    if parsed.netloc == "context":
        return _parse_context_uri(raw_uri=uri, path_parts=path_parts)

    entry = _resolve_enabled_vault(catalog=catalog, vault_id=parsed.netloc)
    kind, value = _parse_vault_resource(path_parts)
    if value is not None:
        value = decode_resource_segment(value, allow_slash=kind in _PATH_KINDS)
    _validate_kind_value(kind=kind, value=value, entry=entry)
    return McpResourceUri(
        raw_uri=uri,
        normalized_uri=_normalize_vault_resource_uri(kind=kind, vault_id=entry.vault_id, value=value),
        kind=kind,
        vault_id=entry.vault_id,
        value=value,
    )


def _parse_context_uri(*, raw_uri: str, path_parts: list[str]) -> McpResourceUri:
    if len(path_parts) != 2 or path_parts[0] != "packs":
        _raise_invalid_resource_uri("unsupported context resource URI")
    pack_id = decode_resource_segment(path_parts[1], allow_slash=False)
    return McpResourceUri(
        raw_uri=raw_uri,
        normalized_uri=f"vault://context/packs/{encode_resource_segment(pack_id)}",
        kind="context_pack",
        vault_id=None,
        value=pack_id,
    )


def _parse_vault_resource(path_parts: list[str]) -> tuple[McpResourceKind, str | None]:
    if len(path_parts) == 2:
        first, second = path_parts
        if first == "documents":
            return "document", second
        if first == "pages":
            return "page", second
        if first == "sources":
            return "source", second
        if first == "concepts":
            return "concept", second
        if first == "decisions":
            return "decision", second
        if first == "issues":
            return "issue", second
        if first == "timeline" and second == "recent":
            return "timeline_recent", None
        if first == "context" and second == "current":
            return "context_current", None
    if len(path_parts) == 3 and path_parts[0] == "graph" and path_parts[1] == "entities":
        return "graph_entity", path_parts[2]
    _raise_invalid_resource_uri("unsupported resource URI")


def _resolve_enabled_vault(*, catalog: VaultCatalog, vault_id: str) -> VaultCatalogEntry:
    if not vault_id:
        _raise_invalid_resource_uri("resource URI must include vault_id")
    try:
        entry = catalog.resolve(vault_id)
    except CatalogError as exc:
        raise McpProtocolError(
            kind="invalid_parameter",
            payload=McpErrorPayload(
                code="unknown_vault_id",
                message=str(exc),
                severity="error",
                affected_vault_ids=(vault_id,),
                recovery_hint="Use a registered enabled vault_id.",
            ),
        ) from exc
    if not entry.enabled:
        raise McpProtocolError(
            kind="invalid_parameter",
            payload=McpErrorPayload(
                code="vault_disabled",
                message=f"vault_id is disabled: {vault_id}",
                severity="error",
                affected_vault_ids=(vault_id,),
                recovery_hint="Enable the Vault entry or choose another vault_id.",
            ),
        )
    return entry


def _path_parts(path: str) -> list[str]:
    if not path.startswith("/"):
        _raise_invalid_resource_uri("resource URI path must be absolute")
    parts = path.removeprefix("/").split("/")
    if not parts or any(part == "" for part in parts):
        _raise_invalid_resource_uri("resource URI path contains empty segments")
    return parts


def _validate_kind_value(*, kind: McpResourceKind, value: str | None, entry: VaultCatalogEntry) -> None:
    if kind in ("timeline_recent", "context_current"):
        if value is not None:
            _raise_invalid_resource_uri("resource URI must not include a value")
        return
    if value is None:
        _raise_invalid_resource_uri("resource URI value is required")
    if kind in _PATH_KINDS:
        if not value.endswith(".md"):
            _raise_invalid_resource_uri("document resources must point to Markdown files")
        if kind == "page" and not _same_or_child(value, "wiki"):
            _raise_invalid_resource_uri("page resources must stay under wiki/")
        if not any(_same_or_child(value, scope) for scope in entry.content_scopes):
            _raise_invalid_resource_uri("document resource is outside enabled content scopes", vault_id=entry.vault_id)


def _validate_decoded_value(value: str, *, allow_slash: bool) -> None:
    if not value:
        _raise_invalid_resource_uri("resource URI value must not be empty")
    if value.startswith("/"):
        _raise_invalid_resource_uri("resource URI value must not be an absolute path")
    if "/" in value and not allow_slash:
        _raise_invalid_resource_uri("resource URI value must be a single opaque segment")
    parts = value.split("/") if allow_slash else (value,)
    if any(part in {"", ".", ".."} for part in parts):
        _raise_invalid_resource_uri("resource URI value contains unsupported path segments")
    if PurePosixPath(value).is_absolute():
        _raise_invalid_resource_uri("resource URI value must not be an absolute path")


def _normalize_vault_resource_uri(*, kind: McpResourceKind, vault_id: str, value: str | None) -> str:
    if kind == "document":
        return f"vault://{vault_id}/documents/{encode_resource_segment(_required_value(value))}"
    if kind == "page":
        return f"vault://{vault_id}/pages/{encode_resource_segment(_required_value(value))}"
    if kind == "source":
        return f"vault://{vault_id}/sources/{encode_resource_segment(_required_value(value))}"
    if kind == "concept":
        return f"vault://{vault_id}/concepts/{encode_resource_segment(_required_value(value))}"
    if kind == "decision":
        return f"vault://{vault_id}/decisions/{encode_resource_segment(_required_value(value))}"
    if kind == "issue":
        return f"vault://{vault_id}/issues/{encode_resource_segment(_required_value(value))}"
    if kind == "timeline_recent":
        return f"vault://{vault_id}/timeline/recent"
    if kind == "context_current":
        return f"vault://{vault_id}/context/current"
    if kind == "graph_entity":
        return f"vault://{vault_id}/graph/entities/{encode_resource_segment(_required_value(value))}"
    raise AssertionError(f"unsupported vault resource kind: {kind}")


def _required_value(value: str | None) -> str:
    if value is None:
        raise AssertionError("resource value is required")
    return value


def _same_or_child(path: str, parent: str) -> bool:
    return path == parent or path.startswith(f"{parent}/")


def _raise_invalid_resource_uri(message: str, *, vault_id: str | None = None) -> NoReturn:
    raise McpProtocolError(
        kind="invalid_parameter",
        payload=McpErrorPayload(
            code="invalid_resource_uri",
            message=message,
            severity="error",
            affected_vault_ids=(vault_id,) if vault_id else (),
            recovery_hint="Use one of the registered vault:// resource templates.",
        ),
    )
