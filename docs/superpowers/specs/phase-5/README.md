# Phase 5 Design Documents

This folder holds detailed Phase 5 MCP server design documents that would make
`docs/SPEC.md` too long if kept in the top-level contract.

`docs/SPEC.md` remains the canonical product and architecture contract. Files in
this folder explain how Phase 5 should expose Vault Graph to agents through MCP
while preserving the read-only, rebuildable, evidence-first boundary over Vault.

## Documents

| File | Role |
| --- | --- |
| `2026-06-15-phase-5-mcp-server-overview-design.md` | Cross-slice overview, invariants, service-backed tool policy, and handoff map |
| `2026-06-15-phase-5a-mcp-server-foundation-stdio-design.md` | Local stdio server foundation, service construction, error mapping, and Codex configuration examples |
| `2026-06-15-phase-5b-mcp-resources-context-pack-resources-design.md` | Read-only resource templates, URI validation, resource rendering, and generated context-pack resource cache |
| `2026-06-15-phase-5c-mcp-tools-prompts-agent-workflows-design.md` | Service-backed tools, prompt templates, structured output policy, and agent workflow contracts |
| `codex-local-stdio-config.example.json` | Local Codex MCP stdio configuration example for `vg serve --mcp` |

## Reading Order

1. Read `docs/SPEC.md` for the top-level product contract.
2. Read `2026-06-15-phase-5-mcp-server-overview-design.md` for Phase 5
   invariants and dependencies.
3. Read the target slice document before writing an implementation plan.
