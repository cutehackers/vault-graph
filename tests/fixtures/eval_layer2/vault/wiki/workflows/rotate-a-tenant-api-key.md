---
title: "Rotate a tenant API key"
summary: "Issue a new Ledgerline API key for a tenant and expire the old one after an overlap window."
tags: [ledgerline, backend, security]
---

# Rotate a tenant API key

## Steps

1. 고객 관리자 화면 또는 `ledgerctl keys create --org <org_id> --label rotated-YYYYMM`으로 새 key를 만든다.
2. 새 key는 `lk_live_` prefix로 시작하고 한 번만 보여진다. DB에는 SHA-256 hash만 저장한다.
3. 옛 key에 `ledgerctl keys expire --key <key_id> --in 7d`로 7일 뒤 만료를 건다. 바로 지우지 않는다.
4. 고객이 새 key로 바꿨는지 `last_used_at`으로 확인한다.
5. 유출이 의심되면 3번 대신 `--in 0`으로 즉시 만료하고 audit log를 확인한다.

## Notes

- webhook 서명 secret은 API key와 별개다. 서명 secret 교체는 webhook 설정 화면에서 한다.
