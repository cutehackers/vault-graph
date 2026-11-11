---
title: "Ledgerline service architecture"
summary: "Ledgerline is a Go API and a River worker sharing one Postgres database on Fly.io."
tags: [ledgerline, backend, architecture]
---

# Ledgerline service architecture

## Components

- `cmd/api`: chi router 기반 HTTP API. Fly.io app `ledgerline-prod`의 `app` process group.
- `cmd/worker`: River worker. 같은 Fly app의 `worker` process group.
- `cmd/ledgerctl`: 운영용 CLI.
- Postgres: Fly가 아닌 Neon의 managed Postgres 16. 연결은 PgBouncer(transaction mode)를 거친다.
- 파일: invoice PDF는 Cloudflare R2에 저장한다.

## Code layout

`internal/http`(handler), `internal/service`(비즈니스 로직), `internal/db`(sqlc 생성 코드), `internal/jobs`(River job 정의).

## Note

PgBouncer transaction mode라서 `SET`이 아니라 `SET LOCAL`만 쓴다. session 단위 설정은 다음 요청에 섞인다.
