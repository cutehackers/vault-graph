---
title: "Replace Firebase Analytics with PostHog"
summary: "Tidepool product analytics moved to a self-hosted PostHog instance."
tags: [tidepool, mobile, analytics, privacy]
---

# Replace Firebase Analytics with PostHog

## Decision

Tidepool은 Firebase Analytics를 제거하고 self-hosted PostHog(`posthog.tidepool.dev`)로 이벤트를 보낸다.

## Why

- App Store privacy label에서 "Data Used to Track You" 항목을 없애고 싶었다. Firebase SDK가 IDFA 관련 경고를 계속 만들었다.
- 건강 관련 데이터(섭취량)가 Google 서버로 가는 것에 대한 사용자 문의가 두 번 있었다.
- PostHog는 funnel과 retention 화면을 기본 제공해서 Firebase에서 하던 분석을 그대로 할 수 있다.
- self-host 비용은 homelab이 아닌 Hetzner CX22 한 대, 월 약 5유로다.

## Rules

- 이벤트에 섭취량 숫자를 넣지 않는다. `goal_reached` 같은 boolean만 보낸다.
- 사용자가 설정에서 analytics를 끌 수 있다. 기본값은 on이다.
