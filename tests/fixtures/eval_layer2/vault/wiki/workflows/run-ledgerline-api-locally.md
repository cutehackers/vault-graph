---
title: "Run Ledgerline API locally"
summary: "Start Postgres with docker compose, apply migrations and run the API with air."
tags: [ledgerline, backend, dev]
---

# Run Ledgerline API locally

## Steps

1. `cp .env.example .env`. `DATABASE_URL`은 `postgres://ledgerline:ledgerline@localhost:5433/ledgerline`이다(5433 포트: 다른 프로젝트의 Postgres와 충돌을 피한다).
2. `docker compose up -d db mailpit`으로 Postgres 16과 메일 확인용 Mailpit을 띄운다.
3. `make migrate-up`으로 goose migration을 적용한다.
4. `make seed`로 테스트 tenant 두 개(`acme-test`, `globex-test`)와 API key를 만든다. key는 터미널에 한 번만 출력된다.
5. `air`로 API를 띄운다. 코드가 바뀌면 다시 빌드한다. 기본 포트 8080.
6. `make worker`로 River worker를 따로 띄운다. 띄우지 않으면 webhook과 PDF job이 쌓이기만 한다.

## Notes

- Mailpit UI는 http://localhost:8025 이다. invoice 메일을 여기서 본다.
