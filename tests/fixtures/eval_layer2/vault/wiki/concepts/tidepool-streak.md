---
title: "Tidepool streak"
summary: "How Tidepool counts consecutive goal days, including the grace day rule."
tags: [tidepool, mobile, domain]
---

# Tidepool streak

## Definition

streak은 하루 목표량을 연속으로 채운 날 수다. 날짜 경계는 사용자 기기의 시간대 기준 04:00이다(자정이 아니다). 늦게 자는 사용자가 새벽에 마신 물을 전날로 계산하기 위해서다.

## Grace day

- 7일 연속을 채울 때마다 grace day 1개를 받는다. 최대 2개까지 쌓인다.
- 목표를 못 채운 날이 있으면 grace day를 자동으로 하나 써서 streak을 유지한다.
- grace day가 없으면 streak은 0으로 돌아간다.

## Code

`src/domain/streak.ts`의 `computeStreak(logs, goals, tz)`가 순수 함수로 계산한다. 화면은 결과만 읽는다.
