---
title: "Ledgerline webhook retry schedule"
summary: "Failed webhook deliveries retry with exponential backoff for up to 72 hours."
tags: [ledgerline, backend, webhooks]
---

# Ledgerline webhook retry schedule

## Schedule

고객 endpoint가 2xx를 10초 안에 돌려주지 않으면 실패로 본다. 재시도 간격은 1분, 5분, 30분, 2시간, 6시간, 12시간, 이후 12시간마다이며 최초 시도부터 72시간까지 한다.

## Rules

- 72시간이 지나면 delivery를 `failed`로 두고 org owner에게 메일을 보낸다.
- 같은 endpoint가 연속 50번 실패하면 endpoint를 `disabled`로 바꾼다. 고객이 대시보드에서 다시 켠다.
- 각 요청은 `Ledgerline-Signature` header에 `t=<timestamp>,v1=<hmac-sha256>`를 담는다. 고객은 5분 넘게 지난 timestamp를 거절해야 한다.

## Note

event payload는 72시간 뒤 지워진다. 그 뒤로는 replay가 안 된다.
