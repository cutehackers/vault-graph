---
title: "Roll back a Ledgerline production deploy"
summary: "Redeploy the previous image to ledgerline-prod and decide what to do with migrations."
tags: [ledgerline, backend, deploy, incident]
---

# Roll back a Ledgerline production deploy

## Steps

1. `fly releases -a ledgerline-prod`로 직전 정상 release의 image를 찾는다.
2. `fly deploy -a ledgerline-prod --image <previous image> --strategy immediate`로 되돌린다. blue-green보다 빠르다.
3. 문제 release에 migration이 있었다면 바로 down하지 않는다. 새 column 추가 같은 하위 호환 migration은 그대로 둔다.
4. 하위 호환이 깨지는 migration이었다면 incident 채널에서 확인을 받은 뒤 `fly ssh console -a ledgerline-prod -C "goose down"`을 실행한다.
5. River에 쌓인 실패 job은 `riverui`에서 확인하고 원인 수정 뒤 retry한다.
6. incident 기록을 `docs/incidents/YYYY-MM-DD.md`에 남긴다.

## Notes

- migration은 항상 하위 호환으로 쓰는 것이 원칙이라 4번은 거의 일어나지 않는다.
