---
title: "Ledgerline error response format"
summary: "Every API error returns a JSON object with type, code, message and request_id."
tags: [ledgerline, backend, api]
---

# Ledgerline error response format

## Shape

```json
{"error": {"type": "invalid_request", "code": "idempotency_key_reused", "message": "...", "param": "amount", "request_id": "req_01J..."}}
```

## Rules

- `type`은 `invalid_request`, `authentication`, `permission`, `not_found`, `conflict`, `rate_limited`, `internal` 중 하나다.
- `code`는 기계가 읽는 세부 이유다. 문서의 error code 표에 모두 올린다.
- `message`는 영어 한 문장이다. 고객 화면에 그대로 보여주지 말라고 문서에 적었다.
- `request_id`는 모든 응답의 `Request-Id` header와 같다. 지원 문의 때 이 값을 받는다.
