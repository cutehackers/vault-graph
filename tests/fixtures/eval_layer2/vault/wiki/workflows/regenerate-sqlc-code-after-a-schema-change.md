---
title: "Regenerate sqlc code after a schema change"
summary: "Run sqlc generate and vet after editing migrations or queries."
tags: [ledgerline, backend, database]
---

# Regenerate sqlc code after a schema change

## Steps

1. migration을 로컬 DB에 적용한다(`make migrate-up`). sqlc는 `db/migrations/`를 schema로 읽는다.
2. `db/queries/<table>.sql`에 query를 추가한다. 이름 주석은 `-- name: ListInvoicesByOrg :many` 형식이다.
3. `make sqlc`(= `sqlc generate && sqlc vet`)을 실행한다. 결과는 `internal/db/` 아래에 생긴다.
4. 생성 파일은 commit한다. CI는 `sqlc diff`로 생성 결과가 commit과 같은지 검사한다.

## Notes

- `sqlc vet`은 `EXPLAIN`으로 query를 검사하므로 로컬 DB가 떠 있어야 한다.
- sqlc 버전은 `tools.go`가 아니라 `.tool-versions`(mise)로 고정한다. 버전이 다르면 diff가 생긴다.
