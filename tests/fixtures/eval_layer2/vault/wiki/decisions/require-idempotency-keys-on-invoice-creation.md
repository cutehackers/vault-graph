---
title: "Require idempotency keys on invoice creation"
summary: "POST /v1/invoices and POST /v1/payments require an Idempotency-Key header."
tags: [ledgerline, backend, api]
---

# Require idempotency keys on invoice creation

## Decision

Ledgerline의 `POST /v1/invoices`, `POST /v1/payments`는 `Idempotency-Key` header를 필수로 받는다. 없으면 400을 돌려준다.

## Why

- 고객사 POS가 timeout 뒤 자동 재시도를 하면서 같은 invoice가 두 번 만들어진 사고가 있었다(2026-05, 고객 3곳).
- 결제와 연결된 리소스는 중복 생성의 비용이 크다. 환불 처리까지 필요했다.
- 선택 header로 두면 SDK를 쓰지 않는 고객은 보내지 않는다. 필수로 해야 효과가 있다.

## Details

- key와 request body hash, 응답을 `idempotency_records` table에 24시간 보관한다.
- 같은 key에 다른 body가 오면 422 `idempotency_key_reused`를 돌려준다.
- 처리 중인 같은 key가 오면 409를 돌려준다.
