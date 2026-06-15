from __future__ import annotations

from typing import Protocol

from vault_graph.context.context_pack import (
    ContextEvidence,
    ContextEvidenceRef,
    ContextPack,
    ContextPackActualScope,
    ContextPackItem,
    ContextPackWarning,
)
from vault_graph.context.context_pack_serialization import render_context_pack_json


class ContextPackRenderer(Protocol):
    def render_json(self, pack: ContextPack) -> str: ...
    def render_markdown(self, pack: ContextPack) -> str: ...


class DefaultContextPackRenderer:
    def render_json(self, pack: ContextPack) -> str:
        return render_context_pack_json(pack)

    def render_markdown(self, pack: ContextPack) -> str:
        lines = [
            "# Context Pack",
            "",
            "## Goal",
            _markdown_text(pack.goal),
            "",
            "## Scope",
            f"- Pack ID: {_markdown_code_span(pack.pack_id)}",
            f"- Schema: {_markdown_code_span(pack.context_pack_schema_version)}",
            f"- Generated: {_markdown_code_span(pack.generated_at)}",
            f"- Requested Vaults: {_markdown_code_span(_joined(pack.scope.requested.vault_ids))}",
            f"- Requested Content Scopes: {_markdown_code_span(_joined(pack.scope.requested.content_scopes))}",
            f"- Include Cross Vault: {_markdown_code_span(str(pack.scope.requested.include_cross_vault))}",
        ]
        if pack.scope.actual_scopes:
            lines.append("- Actual Scopes:")
            lines.extend(
                f"  - {_markdown_code_span(_actual_scope_label(scope))} "
                f"cross_vault={_markdown_code_span(str(scope.include_cross_vault))} "
                f"scope_key={_markdown_code_span(scope.scope_key)}"
                for scope in pack.scope.actual_scopes
            )
        else:
            lines.append("- Actual Scopes: None")
        lines.extend(["", "## Warnings"])
        if pack.warnings:
            lines.extend(_render_warning(warning) for warning in pack.warnings)
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
            lines.extend(_render_evidence(evidence))
        lines.extend(["", "## Revisions", "### Vault Revisions"])
        if pack.vault_revisions:
            lines.extend(
                f"- {_markdown_code_span(revision.vault_id)}: "
                f"{_markdown_code_span(revision.revision or 'unknown')} "
                f"({_markdown_code_span(revision.revision_kind)})"
                for revision in pack.vault_revisions
            )
        else:
            lines.append("- None")
        lines.extend(["", "### Store Revisions"])
        if pack.store_revisions:
            lines.extend(
                f"- {_markdown_code_span(revision.kind)}: {_markdown_code_span(revision.revision or 'unknown')}, "
                f"vault={_markdown_code_span(revision.vault_id or 'global')}, "
                f"scope={_markdown_code_span(revision.scope_key)}"
                for revision in pack.store_revisions
            )
        else:
            lines.append("- None")
        lines.extend(
            [
                "",
                "## Budget",
                f"- max_tokens: `{pack.budget.max_tokens}`",
                f"- max_evidence_items: `{pack.budget.max_evidence_items}`",
                f"- max_excerpt_tokens: `{pack.budget.max_excerpt_tokens}`",
                f"- used_tokens: `{pack.budget.used_tokens}`",
                f"- omitted_items: `{pack.budget.omitted_items}`",
                "",
                "## Backend",
                _render_backend_use(
                    "metadata_store",
                    pack.backend.metadata_store.name,
                    pack.backend.metadata_store.used,
                ),
                _render_backend_use("keyword_index", pack.backend.keyword_index.name, pack.backend.keyword_index.used),
                _render_backend_use("vector_store", pack.backend.vector_store.name, pack.backend.vector_store.used),
                _render_backend_use("graph_store", pack.backend.graph_store.name, pack.backend.graph_store.used),
                _render_backend_use(
                    "graph_projection",
                    pack.backend.graph_projection.name,
                    pack.backend.graph_projection.used,
                ),
            ]
        )
        return "\n".join(lines) + "\n"


def _render_warning(warning: ContextPackWarning) -> str:
    vaults = ",".join(warning.affected_vault_ids) if warning.affected_vault_ids else "unknown"
    rendered = (
        f"- [{warning.severity}] {_markdown_code_span(warning.code)} "
        f"[{_markdown_text(vaults)}]: {_markdown_text(warning.message)}"
    )
    if warning.recovery_hint:
        rendered += f" Recovery: {_markdown_text(warning.recovery_hint)}"
    return rendered


def _render_evidence(evidence: ContextEvidence) -> list[str]:
    ref = evidence.ref
    location = _evidence_location(evidence)
    truncated = " [truncated]" if evidence.truncated else ""
    lines = [
        f"- {_markdown_code_span(_evidence_ref_label(ref))} {location}{truncated} "
        f"({evidence.excerpt_token_count} tokens)"
    ]
    if evidence.warnings:
        lines.extend(f"  - {_render_warning(warning).removeprefix('- ')}" for warning in evidence.warnings)
    if evidence.excerpt:
        fence = _markdown_fence(evidence.excerpt)
        lines.append("")
        lines.append(f"  {fence}text")
        lines.extend(f"  {line}" for line in evidence.excerpt.splitlines())
        lines.append(f"  {fence}")
    return lines


def _evidence_location(evidence: ContextEvidence) -> str:
    suffix = evidence.anchor or evidence.section
    rendered = f"[{_markdown_text(evidence.ref.vault_id)}] {_markdown_text(evidence.path)}"
    if suffix:
        rendered += f"#{_markdown_text(suffix)}"
    return rendered


def _actual_scope_label(scope: ContextPackActualScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"


def _render_item(item: ContextPackItem) -> list[str]:
    lines = [
        f"- **{_markdown_text(item.title)}**",
        f"  - Summary: {_markdown_text(item.summary)}",
        "  - Evidence: "
        + ", ".join(_markdown_code_span(_evidence_ref_label(ref)) for ref in item.evidence_refs),
    ]
    if item.warnings:
        lines.append("  - Warnings:")
        lines.extend(f"    - {_render_warning(warning).removeprefix('- ')}" for warning in item.warnings)
    return lines


def _render_backend_use(name: str, backend_name: str | None, used: bool) -> str:
    return f"- {name}: {_markdown_code_span(backend_name or 'none')}, used={_markdown_code_span(str(used))}"


def _evidence_ref_label(ref: ContextEvidenceRef) -> str:
    return f"{ref.vault_id}:{ref.document_id}:{ref.chunk_id}"


def _joined(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def _markdown_code_span(value: str) -> str:
    safe = value.replace("\n", " ")
    longest = 0
    current = 0
    for character in safe:
        if character == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    fence = "`" * max(1, longest + 1)
    return f"{fence}{safe}{fence}"


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
