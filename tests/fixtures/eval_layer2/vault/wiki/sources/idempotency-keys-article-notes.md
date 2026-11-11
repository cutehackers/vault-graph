---
title: "Idempotency keys article notes"
summary: "Notes from an article on designing idempotent POST APIs with idempotency keys."
tags: [ledgerline, api, source]
---

# Idempotency keys article notes

## Source

결제 API의 idempotency key 설계를 다룬 글.

## Notes

- key는 클라이언트가 만든다(UUIDv4 권장). 서버는 key + 요청 내용을 함께 저장한다.
- 같은 key, 다른 내용은 오류로 돌려준다. 조용히 첫 응답을 돌려주면 클라이언트 버그가 숨는다.
- 처리 중 상태를 기록해서 동시 요청을 막는다(lock 또는 상태 column).
- 보관 기간은 24시간이 흔하다.
