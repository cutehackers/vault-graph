---
title: "Tidepool daily goal calculation"
summary: "The default daily water goal is derived from body weight and activity level."
tags: [tidepool, mobile, domain]
---

# Tidepool daily goal calculation

## Formula

기본 목표량(ml) = 체중(kg) × 33, 활동량 "높음"이면 +500ml. 결과는 50ml 단위로 반올림하고 1,500~4,000ml 범위로 자른다.

## Rules

- 사용자가 목표를 직접 입력하면 공식을 쓰지 않는다. `goal_source = 'manual'`로 저장한다.
- 체중을 입력하지 않은 사용자는 2,000ml로 시작한다.
- 더운 날 보정(기온 기반)은 날씨 API가 필요해서 v1에 넣지 않았다.

## Note

이 공식은 의료 권고가 아니다. 온보딩 화면에 안내 문구를 둔다.
