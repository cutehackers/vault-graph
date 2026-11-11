---
title: "Run Tidepool on a physical Android device"
summary: "Install the EAS development client on a phone and connect it to the local Metro server."
tags: [tidepool, mobile, android, dev]
---

# Run Tidepool on a physical Android device

## Steps

1. 폰에서 개발자 옵션과 USB debugging을 켠다.
2. `eas build --platform android --profile development`로 development client APK를 만든다. native 의존성이 바뀌지 않았으면 기존 APK를 재사용한다.
3. EAS 페이지의 QR 코드로 APK를 설치한다.
4. 노트북에서 `pnpm start --dev-client`로 Metro를 띄운다.
5. 같은 Wi-Fi가 아니면 `adb reverse tcp:8081 tcp:8081`을 실행하고 USB로 연결한다.
6. 앱에서 Metro 주소를 고른다.

## Troubleshooting

- 회사 Wi-Fi는 기기 간 통신을 막는다. 5번의 `adb reverse`를 쓴다.
- Galaxy 기기는 "절전 모드"에서 알림 예약이 지연된다. 알림 테스트 때는 끈다.
