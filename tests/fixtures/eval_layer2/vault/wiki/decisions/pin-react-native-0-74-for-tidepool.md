---
title: "Pin React Native 0.74 for Tidepool"
summary: "Tidepool stays on React Native 0.74 until Reanimated 3 issues are fixed."
tags: [tidepool, mobile, dependencies]
---

# Pin React Native 0.74 for Tidepool

## Decision

Tidepool은 React Native 0.74(Expo SDK 51)에 고정한다. SDK 52 업그레이드는 보류한다.

## Why

- SDK 52의 New Architecture 기본 활성화에서 `react-native-reanimated` 3.x의 물결 애니메이션(wave progress)이 Android에서 깜빡였다.
- 물결 progress는 메인 화면의 핵심 UI라서 대체가 어렵다.
- 0.74는 아직 보안 패치 대상이다.

## Exit condition

Reanimated 이슈가 고쳐진 버전이 나오고 Android 실기기 3종(Pixel 7, Galaxy A54, Galaxy S23)에서 깜빡임이 없으면 올린다.
