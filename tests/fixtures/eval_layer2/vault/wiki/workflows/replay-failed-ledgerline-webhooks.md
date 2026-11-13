---
title: "Replay failed Ledgerline webhooks"
summary: "Find failed webhook deliveries for a tenant and enqueue them again."
tags: [ledgerline, backend, webhooks]
---

# Replay failed Ledgerline webhooks

## Steps

1. 고객이 webhook 누락을 신고하면 `org_id`와 기간을 받는다.
2. `ledgerctl webhooks failed --org <org_id> --since 48h`로 `failed` 상태 delivery 목록을 본다.
3. 고객 endpoint가 다시 살아났는지 `ledgerctl webhooks ping --org <org_id>`로 확인한다.
4. `ledgerctl webhooks replay --org <org_id> --since 48h --dry-run`으로 대상 수를 본다.
5. `--dry-run` 없이 다시 실행한다. 각 delivery가 새 River job으로 들어간다. 원래 `event_id`는 그대로라서 고객 쪽에서 중복을 거를 수 있다.

## Notes

- 72시간이 지난 event는 payload가 지워져서 replay할 수 없다.
- `ledgerctl`은 `cmd/ledgerctl`에 있는 운영용 CLI다. production에서는 `fly ssh console`로 접속해 실행한다.
