---
title: "Use cursor pagination for list endpoints"
summary: "Ledgerline list endpoints page with an opaque cursor, not offset/limit."
tags: [ledgerline, backend, api]
---

# Use cursor pagination for list endpoints

## Decision

Ledgerline의 목록 API(`GET /v1/invoices` 등)는 opaque cursor(`starting_after`)로 페이지를 넘긴다. `offset`은 받지 않는다.

## Why

- invoice가 계속 추가되는 중에 offset으로 넘기면 같은 항목이 두 번 나오거나 빠진다. 고객사 정산 스크립트에서 중복 집계가 생겼다.
- 큰 offset은 Postgres가 앞 행을 모두 읽어야 해서 느리다. 10만 건 tenant에서 offset 90000 요청이 2초 걸렸다.
- cursor는 `(created_at, id)` 복합 index를 그대로 탄다.

## Format

cursor는 `base64url(created_at|id)`이다. 고객은 내용을 해석하지 말고 그대로 돌려보낸다. `limit` 기본 25, 최대 100.
