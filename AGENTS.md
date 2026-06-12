# AGENTS.md

## Project Boundary

Vault Graph is a read-only, rebuildable access layer over Vault. Do not make
Vault Graph a durable knowledge source, and do not add behavior that edits,
renames, rewrites, or deletes Vault content.

## Source Documents

- Read `docs/SPEC.md` before changing architecture, indexing, retrieval, graph,
  or context-pack behavior.
- Follow `docs/CONVENTIONS.md` for Python style and naming.

## Documentation Operation Rules

Use these rules when writing specs, implementation plans, or prompt templates.

- Keep prompt templates compact. Move repeatable repository policy here instead
  of duplicating it inside every goal prompt.
- `docs/PATCH_LOG.md` records corrections made after review or verification.
  Use it only when a plan, spec, or implementation is changed because a mismatch,
  defect, or risk was found.
- New patch entries must match the existing project style:
  `## YYYY-MM-DD - <Short Title>`, then `**Trigger:**`, `**Scope:**`,
  `**Core Values Protected:**`, `**Changes Applied:**`, and
  `**Verification:**`.
- `docs/DECISIONS.md` records accepted product, architecture, and policy
  decisions only. Do not add pending decisions there.
- If a decision needs user judgment, keep it in the active plan under
  `Open Decisions` with context, options, trade-offs, and a recommendation.
  Move it to `docs/DECISIONS.md` only after approval, using the existing
  `Question`, `Decision`, `Reason`, and `Implications` style.
- For both logs, be short, specific, and evidence-linked. Do not copy long
  implementation-plan content into them.

## 🤖 Software Engineering Philosophy

> **Core Principle:**
> "Always prioritize **'Deep Modules'**, **'Less Complexity'**, and **'Changeability'** over quick implementations."

### 1. Complexity & Changeability

- **Definition of Complexity:** Anything in the software structure that makes it hard to understand or modify.
- **The Goal:** Maintain a codebase where changes are easy and predictable. A good codebase is one that rewards future development rather than punishing it.
- **Anti-Entropy:** Actively resist "Software Entropy." Do not just add code; improve the design with every change. If a task increases entropy, **refactor first**, then implement.

### 2. Deep Modules vs. Shallow Modules

- **Deep Modules (Preferred):** High functionality hidden behind a simple, stable interface. These modules encapsulate complexity and reduce the cognitive load for both humans and AI.
- **Shallow Modules (Avoid):** Small pieces of code with complex interfaces that expose internal logic. These lead to fragmented, fragile systems.
- **Information Hiding:** Hide implementation details. The consumer of a module should never need to know _how_ it works, only _what_ it does.

### 3. Strategic Programming

- **Think Strategically:** Don't just solve the immediate problem (Tactical Programming). Design for the long-term health of the system.
- **Shared Design Concept:** Before coding, ensure a shared understanding of the architecture. Reach a "shared mental model" through rigorous planning and questioning (e.g., "Grilling" process).
- **Ubiquitous Language:** Use consistent terminology across documentation, design, and code to minimize communication gaps.

### 4. Development Workflow & Safety

- **Test-Driven Safety:** Use **TDD** and **Static Typing** (like Dart/Flutter) as a "speed limit." Never outrun your headlights; take small, verifiable steps.
- **Interface-First:** Focus on designing robust interfaces. Delegate the tactical implementation to the AI while keeping it strictly within the defined boundaries.
- **Modern Standards:** Always prioritize improved versions of methods and current industry standards over legacy or deprecated patterns.

### 5. Human-AI Collaboration Role

- **Human:** **Strategic Leader & Architect.** Focus on high-level design, module boundaries, and complexity management.
- **AI:** **Tactical Programmer.** Execute implementation details, refactor according to the philosophy, and ensure code adheres to the strategic boundaries.

## Coding Guidelines

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
