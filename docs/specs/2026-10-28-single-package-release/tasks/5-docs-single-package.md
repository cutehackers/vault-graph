# Task 5: Document single-package publishing in PUBLISHING, ARCHITECTURE and DECISIONS

## id

5

## title

Document single-package publishing in PUBLISHING, ARCHITECTURE and DECISIONS

## goal

Maintainers can read that PyPI receives only `vault-graph`, with the modules bundled inside it, and why module publishing is deferred. This records the Intent 2 policy, and the decision that keeps a path back to separate publishing (Intent [가정]).

## files

- `docs/PUBLISHING.md`
- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`

## blockers

none

## acceptance

- A-11

## checks

- `grep -n '독립 배포 패키지' docs/ARCHITECTURE.md` (must find nothing)
- `grep -nE 'Question|Decision|Reason|Implications' docs/DECISIONS.md | tail -n 8`
- `git diff main -- docs/PUBLISHING.md` (the `Release Verification` section is unchanged)

## done-when

- [ ] `docs/PUBLISHING.md` states that only `vault-graph` is published, that the 5 modules ship inside its wheel, and that no module Trusted Publisher is registered. `Release Verification` is unchanged.
- [ ] In `docs/ARCHITECTURE.md`, lines 132 and 177 say "독립 모듈 5개(현재 `vault-graph` wheel에 포함해 배포)". The distribution-name table is kept.
- [ ] `docs/DECISIONS.md` has a new Question/Decision/Reason/Implications entry deferring module publishing to PyPI. The 2026-10-04 naming decision is kept.
- [ ] `docs/PATCH_LOG.md` is not changed (질문4).
