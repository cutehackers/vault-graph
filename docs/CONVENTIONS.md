# Python Conventions

This document defines the Python conventions for Vault Graph. It is based on the
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html),
with project-specific rules kept short enough for agents to follow consistently.

## Core Principles

- Write code that is easy to read, test, and delete.
- Keep Vault Graph as a read-only, rebuildable projection over Vault.
- Prefer explicit domain boundaries over generic shared buckets.
- Make source ownership clear through precise module, class, and function names.

## Module Naming

Python module names must be `snake_case` and must describe the behavior they own.
Module naming is a design decision, not a cosmetic choice.

Avoid vague names such as `utils.py`, `helpers.py`, `common.py`, `manager.py`,
and `processor.py`.

Names must describe domain responsibility or runtime behavior. If a module cannot
be named precisely, split the responsibility before writing more code.

Prefer names that describe domain responsibility:

- `vault_loading.py`
- `document_chunking.py`
- `metadata_indexing.py`
- `graph_projection.py`
- `context_pack_building.py`
- `token_refresh.py`
- `user_permissions.py`

Avoid generic buckets:

- `utils.py`
- `helpers.py`
- `common.py`
- `manager.py`
- `processor.py`

## File And Package Structure

- One module should own one clear responsibility.
- Keep public APIs close to the domain they serve.
- Do not hide cross-cutting behavior in generic modules.
- Split large modules when naming becomes vague or tests become hard to target.
- Keep generated, cached, or indexed state separate from durable source files.

## Imports

- Use absolute imports for project code.
- Keep imports grouped and ordered by the formatter/linter.
- Do not use wildcard imports.
- Avoid import-time side effects such as filesystem writes, network calls, or
  index rebuilds.

## Formatting

Use automated formatting.

- Use `ruff format` or `black`.
- Set line length to `120`.
- Do not manually format code in ways that fight the formatter.
- Use one formatting standard across the whole project.

## Linting

Use `ruff` as the default linter.

Recommended checks:

- unused imports
- unused variables
- import ordering
- common bug patterns
- unsafe exception handling
- overly broad constructs

Linting should run in CI and before commits.

## Type Hints

Use type hints for public functions, service boundaries, data models, and
non-trivial internal logic.

```python
def calculate_total(items: list[LineItem]) -> Money:
    ...
```

Avoid unnecessary `Any`. If the data shape is unclear, define a type, dataclass,
or Pydantic model.

## Functions

- Keep functions small and focused on one behavior.
- Use descriptive verb phrases for function names.
- Do not use the `effective_` prefix in function names, variables, fields, or
  public output keys. When naming a value that contrasts with a requested or
  configured value, use `actual_` for the value Vault Graph will really apply.
- Prefer returning values over mutating hidden shared state.
- Make side effects visible in names or call sites.
- Do not catch broad exceptions unless the boundary requires it and the error is
  logged or converted into a clear domain error.

## Classes

- Use classes when state, lifecycle, or a stable interface is needed.
- Prefer dataclasses or Pydantic models for structured data.
- Do not create `Manager`, `Helper`, or `Processor` classes without a precise
  domain name.
- Keep constructors lightweight and free of expensive work.

## Tests

- Add focused tests for parsing, indexing, retrieval ranking, graph projection,
  and context pack assembly.
- Tests should describe observable behavior, not implementation details.
- Prefer deterministic fixtures over live services.
- Keep tests close to the boundary they validate.

## Documentation

- Document public APIs, non-obvious decisions, and project boundaries.
- Keep comments short and useful.
- Do not restate code in comments.
- When behavior protects the Vault boundary, document that explicitly.
