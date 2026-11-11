---
title: "Deploy Ledgerline to staging"
summary: "Merging to main deploys ledgerline-staging on Fly.io; manual deploy is also possible."
tags: [ledgerline, backend, deploy]
---

# Deploy Ledgerline to staging

## Steps

1. PR을 `main`에 merge하면 GitHub Actions `deploy-staging` job이 `flyctl deploy --app ledgerline-staging`을 실행한다.
2. 배포 전에 `release_command`로 `goose up`이 돈다. migration이 실패하면 배포가 멈추고 이전 machine이 그대로 남는다.
3. 수동 배포가 필요하면 `fly deploy -a ledgerline-staging --strategy rolling`을 쓴다.
4. 배포 뒤 `make smoke ENV=staging`으로 health check, invoice 생성, webhook 수신 세 가지를 확인한다.

## Notes

- staging DB는 매주 일요일 production 익명화 덤프로 다시 채워진다.
- staging webhook은 `webhook.site` 대신 내부 `hookcatcher` 앱으로 받는다.
