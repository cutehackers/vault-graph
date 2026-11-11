---
title: "Tidepool CI pipeline"
summary: "GitHub Actions jobs for Tidepool: checks on PR, EAS preview build on label, OTA on main."
tags: [tidepool, mobile, ci]
---

# Tidepool CI pipeline

## Jobs

- `checks` (모든 PR): `pnpm typecheck`, `pnpm lint`, `pnpm test`, `pnpm i18n:check`. 약 4분.
- `preview-build` (PR에 `preview` label이 붙을 때): `eas build --profile preview`로 내부 배포용 build를 만들고 QR 링크를 PR comment로 단다.
- `ota-main` (main push): JS만 바뀐 경우 `eas update --branch production`으로 OTA를 보낸다. native 변경이 감지되면(`expo-fingerprint` 값이 다르면) OTA를 건너뛰고 경고를 단다.

## Secrets

`EXPO_TOKEN`, `SENTRY_AUTH_TOKEN`만 GitHub secret에 있다. 서명 credentials는 EAS에 있다.
