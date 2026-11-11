---
title: "Ledgerline CI pipeline"
summary: "GitHub Actions for Ledgerline: lint, sqlc diff, tests against Postgres, staging deploy."
tags: [ledgerline, backend, ci]
---

# Ledgerline CI pipeline

## Jobs

1. `lint`: `golangci-lint run`, `make lint-rls`.
2. `sqlc`: `sqlc diff`로 생성 코드가 commit과 같은지 확인한다.
3. `test`: service container로 Postgres 16을 띄우고 `go test ./... -race`. migration을 먼저 적용한다.
4. `deploy-staging`: main에서만. 1~3이 통과하면 staging에 배포한다.
5. `release-please`: main에서만. release PR을 열거나 갱신한다.

## Notes

- test는 tenant마다 다른 DB role로 돌려서 RLS 누락을 잡는 test helper(`testdb.AsOrg`)를 쓴다.
- 평균 7분. 가장 느린 것은 `-race` test다.
