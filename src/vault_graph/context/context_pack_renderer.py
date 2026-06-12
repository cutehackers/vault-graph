from __future__ import annotations

from typing import Protocol

from vault_graph.context.context_pack import ContextPack, ContextPackItem
from vault_graph.context.context_pack_serialization import render_context_pack_json


class ContextPackRenderer(Protocol):
    def render_json(self, pack: ContextPack) -> str: ...
    def render_markdown(self, pack: ContextPack) -> str: ...


class DefaultContextPackRenderer:
    def render_json(self, pack: ContextPack) -> str:
        return render_context_pack_json(pack)

    def render_markdown(self, pack: ContextPack) -> str:
        lines = [
            f"# Context Pack: {_markdown_text(pack.goal)}",
            "",
            f"- Pack ID: `{pack.pack_id}`",
            f"- Schema: `{pack.context_pack_schema_version}`",
            f"- Generated: `{pack.generated_at}`",
            f"- Requested Vaults: `{', '.join(pack.scope.requested.vault_ids)}`",
            "",
            "## Budget",
            f"- max_tokens: `{pack.budget.max_tokens}`",
            f"- max_evidence_items: `{pack.budget.max_evidence_items}`",
            f"- max_excerpt_tokens: `{pack.budget.max_excerpt_tokens}`",
            f"- used_tokens: `{pack.budget.used_tokens}`",
            f"- omitted_items: `{pack.budget.omitted_items}`",
            "",
            "## Backend",
            _render_backend_use("metadata_store", pack.backend.metadata_store.name, pack.backend.metadata_store.used),
            _render_backend_use("keyword_index", pack.backend.keyword_index.name, pack.backend.keyword_index.used),
            _render_backend_use("vector_store", pack.backend.vector_store.name, pack.backend.vector_store.used),
            _render_backend_use("graph_store", pack.backend.graph_store.name, pack.backend.graph_store.used),
            _render_backend_use(
                "graph_projection",
                pack.backend.graph_projection.name,
                pack.backend.graph_projection.used,
            ),
            "",
            "## Vault Revisions",
        ]
        if pack.vault_revisions:
            lines.extend(
                f"- `{_markdown_text(revision.vault_id)}`: `{_markdown_text(revision.revision or 'unknown')}` "
                f"(`{revision.revision_kind}`)"
                for revision in pack.vault_revisions
            )
        else:
            lines.append("- None")
        lines.extend(["", "## Store Revisions"])
        if pack.store_revisions:
            lines.extend(
                f"- `{revision.kind}`: `{_markdown_text(revision.revision or 'unknown')}`, "
                f"vault=`{_markdown_text(revision.vault_id or 'global')}`, "
                f"scope=`{_markdown_text(revision.scope_key)}`"
                for revision in pack.store_revisions
            )
        else:
            lines.append("- None")
        lines.extend(
            [
                "",
                "## Warnings",
            ]
        )
        if pack.warnings:
            lines.extend(
                f"- [{warning.severity}] `{warning.code}`: {_markdown_text(warning.message)}"
                for warning in pack.warnings
            )
        else:
            lines.append("- None")
        sections = (
            ("Decisions", pack.decisions),
            ("Constraints", pack.constraints),
            ("Open Questions", pack.open_questions),
            ("Current State", pack.current_state),
            ("Relevant Pages", pack.relevant_pages),
            ("Relevant Sources", pack.relevant_sources),
        )
        for title, items in sections:
            lines.extend(["", f"## {title}"])
            if not items:
                lines.append("- None")
                continue
            for item in items:
                lines.extend(_render_item(item))
        lines.extend(["", "## Evidence"])
        if not pack.evidence:
            lines.append("- None")
        for evidence in pack.evidence:
            ref = evidence.ref
            lines.append(
                f"- `{ref.vault_id}:{ref.document_id}:{ref.chunk_id}` "
                f"{_markdown_text(evidence.path)} ({evidence.excerpt_token_count} tokens)"
            )
            if evidence.warnings:
                for warning in evidence.warnings:
                    lines.append(f"  - [{warning.severity}] `{warning.code}`: {_markdown_text(warning.message)}")
            if evidence.excerpt:
                fence = _markdown_fence(evidence.excerpt)
                lines.append("")
                lines.append(f"  {fence}text")
                lines.extend(f"  {line}" for line in evidence.excerpt.splitlines())
                lines.append(f"  {fence}")
        return "\n".join(lines) + "\n"


def _render_item(item: ContextPackItem) -> list[str]:
    lines = [
        f"- **{_markdown_text(item.title)}**",
        f"  - Summary: {_markdown_text(item.summary)}",
        "  - Evidence: "
        + ", ".join(f"`{ref.vault_id}:{ref.document_id}:{ref.chunk_id}`" for ref in item.evidence_refs),
    ]
    if item.warnings:
        lines.append("  - Warnings:")
        lines.extend(
            f"    - [{warning.severity}] `{warning.code}`: {_markdown_text(warning.message)}"
            for warning in item.warnings
        )
    return lines


def _render_backend_use(name: str, backend_name: str | None, used: bool) -> str:
    rendered_name = _markdown_text(backend_name or "none")
    return f"- {name}: `{rendered_name}`, used=`{used}`"


def _markdown_text(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for character in ("`", "#", "*", "_", "[", "]", "(", ")", "<", ">", "|"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped.replace("\n", " ")


def _markdown_fence(value: str) -> str:
    longest = 0
    current = 0
    for character in value:
        if character == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return "`" * max(3, longest + 1)
