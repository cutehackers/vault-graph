---
title: "Promote a Ledgerline release to production"
summary: "Promote the image tested on staging to ledgerline-prod with a blue-green deploy."
tags: [ledgerline, backend, deploy]
---

# Promote a Ledgerline release to production

## Steps

1. staging smoke가 통과한 image digest를 `fly releases -a ledgerline-staging --image`로 확인한다.
2. GitHub Actions에서 `promote-production` workflow를 수동 실행하고 digest를 입력한다. 같은 image를 다시 빌드하지 않는다.
3. workflow가 `fly deploy -a ledgerline-prod --image <digest> --strategy bluegreen`을 실행한다.
4. green machine이 health check를 통과하면 트래픽이 넘어간다. 실패하면 blue가 그대로 남는다.
5. Grafana의 "Ledgerline API" dashboard에서 5xx 비율과 p95 latency를 15분 지켜본다.
6. release-please release가 있으면 고객 공지 메일을 보낸다.

## Notes

- 금요일 오후 4시 이후에는 promote하지 않는다.
