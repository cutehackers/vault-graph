---
title: "Tidepool notification scheduler"
summary: "How Tidepool refills up to 64 pending local notifications within quiet hours."
tags: [tidepool, mobile, notifications]
---

# Tidepool notification scheduler

## Behavior

- 앱이 foreground로 올 때와 설정이 바뀔 때 `rescheduleAll()`이 돈다.
- 기존 예약을 모두 취소하고, 앞으로 4일치 알림을 간격(기본 90분)에 맞춰 다시 예약한다. iOS 상한 64개를 넘지 않게 자른다.
- 수면 시간(기본 23:00~07:00)에는 예약하지 않는다.
- 오늘 목표를 이미 채웠으면 오늘 남은 알림은 예약하지 않는다.

## Known issue

앱을 4일 넘게 열지 않으면 알림이 끊긴다. background fetch(`expo-background-fetch`)로 하루 한 번 다시 채우는 방안을 검토 중이다. Android에서 제조사 절전 정책 때문에 확실하지 않다.
