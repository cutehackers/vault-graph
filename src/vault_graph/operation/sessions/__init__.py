"""Agent session normalization (area M19, spec 2026-11-05 §4.2.2, 결정18).

Adapters turn raw agent session records into ``vg-session-jsonl/1`` lines. This area is pure code:
composition reads the source files and writes the result. Only M01 may be imported here, and no
feature area imports this one. Import the owning module directly; this package exports nothing.
"""
