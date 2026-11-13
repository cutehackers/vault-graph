---
title: "Create and apply a Ledgerline migration"
summary: "Write a goose SQL migration, apply it locally and add RLS policies for new tenant tables."
tags: [ledgerline, backend, database]
---

# Create and apply a Ledgerline migration

## Steps

1. `make migration name=add_credit_notes`로 `db/migrations/<timestamp>_add_credit_notes.sql`을 만든다.
2. `-- +goose Up`과 `-- +goose Down` 두 부분을 모두 쓴다. Down이 없으면 CI가 실패한다.
3. 새 table이 tenant 데이터면 `org_id uuid not null`과 RLS policy를 같은 migration에 넣는다. `make lint-rls`가 policy 없는 tenant table을 찾아낸다.
4. `make migrate-up`으로 로컬에 적용하고 `make migrate-down && make migrate-up`으로 되돌리기도 시험한다.
5. query가 필요하면 [[regenerate-sqlc-code-after-a-schema-change|Regenerate sqlc code after a schema change]]를 이어서 한다.

## Rules

- 운영 table에 column을 추가할 때 `NOT NULL DEFAULT`는 두 단계로 나눈다: nullable로 추가 → backfill → constraint 추가.
- index는 `CREATE INDEX CONCURRENTLY`로 만들고, 그 migration 파일에는 `-- +goose NO TRANSACTION`을 붙인다.
