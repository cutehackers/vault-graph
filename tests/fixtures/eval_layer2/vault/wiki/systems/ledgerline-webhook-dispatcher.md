---
title: "Ledgerline webhook dispatcher"
summary: "How events become signed HTTP deliveries through River jobs."
tags: [ledgerline, backend, webhooks]
---

# Ledgerline webhook dispatcher

## Flow

1. 서비스 코드가 상태 변경과 같은 transaction에서 `events` 행과 `DeliverWebhook` River job을 넣는다.
2. worker가 job을 받아 org의 활성 endpoint마다 delivery 행을 만든다.
3. payload를 서명하고 POST한다. timeout 10초.
4. 결과(status code, 응답 앞 1KB, 걸린 시간)를 `webhook_attempts`에 남긴다.
5. 실패면 River의 retry 정책([[ledgerline-webhook-retry-schedule|Ledgerline webhook retry schedule]])으로 다시 넣는다.

## Limits

- org당 동시 발송 5개. River의 queue를 org hash로 나눠서 한 고객의 느린 endpoint가 다른 고객을 막지 않게 했다.
- 응답 body는 1KB만 저장한다.
