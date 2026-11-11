---
title: "Ledgerline invoice lifecycle"
summary: "Invoice states draft, open, paid, void and uncollectible and the allowed transitions."
tags: [ledgerline, backend, domain]
---

# Ledgerline invoice lifecycle

## States

- `draft`: 수정 가능. 번호가 아직 없다.
- `open`: 확정됨. invoice 번호(`INV-<org prefix>-<seq>`)가 붙고 고객에게 발송된다. 금액 수정 불가.
- `paid`: 결제 완료.
- `void`: 취소. 번호는 재사용하지 않는다.
- `uncollectible`: 회수 불가로 처리. 나중에 결제되면 `paid`로 갈 수 있다.

## Transitions

draft → open → paid. open → void. open → uncollectible → paid.
`paid`와 `void`는 끝 상태다. 이미 paid인 invoice를 고치려면 credit note를 발행한다.

## Events

상태가 바뀔 때마다 `invoice.<state>` webhook event가 생긴다(예: `invoice.paid`).
