---
title: "Run Ledgerline jobs on River"
summary: "Background jobs moved from Redis + Asynq to River, a Postgres-backed queue."
tags: [ledgerline, backend, jobs]
---

# Run Ledgerline jobs on River

## Decision

Ledgerline의 background job(webhook 발송, PDF 생성, 정기 청구)은 River(Postgres 기반 Go job queue)로 돌린다. [[use-redis-and-asynq-for-ledgerline-jobs|Use Redis and Asynq for Ledgerline jobs]]를 대체한다.

## Why

- job을 비즈니스 데이터와 같은 transaction에서 넣을 수 있다. invoice insert는 성공했는데 webhook job enqueue가 실패하는 경우가 없어진다(transactional enqueue).
- Redis를 운영할 필요가 없어진다. Fly.io의 Upstash Redis 비용과 연결 끊김 알림이 사라진다.
- 현재 job 처리량은 초당 20건 미만이다. Postgres로 충분하다.

## Trade-offs

- job table이 커지면 vacuum 부담이 생긴다. 완료 job은 River의 cleaner로 7일 뒤 지운다.
- Asynq web UI 대신 River UI(`riverui`)를 내부망에 띄운다.
