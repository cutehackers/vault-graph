---
title: "Use Sentry for Tidepool crash reports"
summary: "Tidepool sends crash reports and JS errors to Sentry."
tags: [tidepool, mobile, observability]
---

# Use Sentry for Tidepool crash reports

## Decision

Tidepool의 crash report와 JS error는 Sentry(`@sentry/react-native`)로 보낸다.

## Why

- Firebase Crashlytics를 PostHog 전환 때 함께 걷어냈다. crash 수집이 비게 됐다.
- Sentry는 EAS Build와 source map 업로드가 공식 지원된다. `sentry-expo` plugin 설정만 하면 된다.
- 무료 tier 월 5천 event로 현재 DAU에 충분하다.

## Rules

- `beforeSend`에서 섭취량, reminder 시간 같은 사용자 데이터를 지운다.
- release 이름은 `tidepool@<version>+<buildNumber>`로 맞춘다.
