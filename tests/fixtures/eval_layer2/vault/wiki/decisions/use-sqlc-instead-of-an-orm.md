---
title: "Use sqlc instead of an ORM"
summary: "Ledgerline writes SQL by hand and generates Go code with sqlc; no GORM."
tags: [ledgerline, backend, database]
---

# Use sqlc instead of an ORM

## Decision

Ledgerline의 DB 접근은 sqlc로 생성한 Go 코드만 쓴다. GORM이나 ent 같은 ORM은 쓰지 않는다.

## Why

- RLS, `SET LOCAL`, CTE, `FOR UPDATE SKIP LOCKED` 같은 Postgres 기능을 직접 써야 한다. ORM은 이걸 raw query로 빠지게 만든다.
- sqlc는 compile time에 query와 schema를 검사한다. column 이름 오타가 CI에서 잡힌다.
- 생성된 코드가 평범한 Go 함수라서 디버깅이 쉽다.

## Consequences

- query는 `db/queries/*.sql`에 둔다. 동적 필터가 많은 검색 API는 `squirrel`로 예외 처리한다.
