---
title: "Use Redis and Asynq for Ledgerline jobs"
summary: "Superseded. Ledgerline first ran background jobs on Redis with Asynq."
tags: [ledgerline, backend, jobs, superseded]
---

# Use Redis and Asynq for Ledgerline jobs

> Status: superseded by [[run-ledgerline-jobs-on-river|Run Ledgerline jobs on River]] (2026-07).

## Decision (old)

Ledgerline 초기에는 background job을 Redis + Asynq로 돌리기로 했다.

## Why (at the time)

- Asynq는 retry, scheduled task, web UI를 모두 제공했다.
- 팀원이 이전 회사에서 Asynq를 써 봐서 학습 비용이 없었다.
- Redis는 rate limiting에도 쓸 계획이었다.

## Why it was reversed

rate limiting을 Fly.io proxy 쪽으로 옮기면서 Redis를 쓸 이유가 job queue 하나만 남았다. enqueue와 DB write가 분리돼 webhook 누락이 두 번 생겼다.
