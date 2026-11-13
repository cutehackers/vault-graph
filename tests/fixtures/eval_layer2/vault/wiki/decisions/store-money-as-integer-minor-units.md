---
title: "Store money as integer minor units"
summary: "Ledgerline stores amounts as bigint minor units with an ISO 4217 currency code."
tags: [ledgerline, backend, money]
---

# Store money as integer minor units

## Decision

Ledgerline은 금액을 `bigint` minor unit(예: KRW는 원, USD는 cent)과 `currency` 코드(ISO 4217)로 저장한다. `numeric`이나 float을 쓰지 않는다.

## Why

- Go의 `float64`로 합계를 계산하다 0.01 차이가 난 invoice가 실제로 나왔다.
- `numeric`은 정확하지만 Go 쪽에서 `pgtype.Numeric` 변환이 번거롭고 JSON 직렬화 규칙이 제각각이었다.
- 정수 minor unit은 Stripe 등 결제사 API와 같은 표현이라 변환이 없다.

## Notes

- JPY, KRW처럼 소수 자리가 0인 통화는 minor unit = major unit이다.
- 표시용 포맷팅은 클라이언트가 한다. API는 `amount`(정수)와 `currency`만 준다.
