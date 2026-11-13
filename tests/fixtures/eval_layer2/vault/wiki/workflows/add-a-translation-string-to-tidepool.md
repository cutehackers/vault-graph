---
title: "Add a translation string to Tidepool"
summary: "Add a new i18n key in Korean and English and check for missing keys."
tags: [tidepool, mobile, i18n]
---

# Add a translation string to Tidepool

## Steps

1. `src/i18n/locales/en.json`에 key를 추가한다. key는 `screen.element.state` 형식이다(예: `home.goalBanner.reached`).
2. `src/i18n/locales/ko.json`에 같은 key로 한국어 문구를 넣는다.
3. 코드에서는 `t('home.goalBanner.reached')`로 쓴다. 문자열을 직접 쓰면 eslint `i18next/no-literal-string`이 막는다.
4. `pnpm i18n:check`로 두 파일의 key 차이를 검사한다. CI에서도 같은 검사가 돈다.
5. 복수형은 `_one`, `_other` 접미사를 쓴다. 한국어는 `_other`만 있어도 된다.

## Notes

- 알림 문구는 `src/notifications/messages.ts`에서 따로 관리한다. i18n 파일이 아니다.
