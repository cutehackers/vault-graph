---
title: "Update Tidepool app icon and splash screen"
summary: "Replace icon and splash assets and rebuild native projects."
tags: [tidepool, mobile, design]
---

# Update Tidepool app icon and splash screen

## Steps

1. 디자이너에게 1024×1024 PNG icon과 Android adaptive icon foreground(432×432, 투명 배경)를 받는다.
2. `assets/icon.png`, `assets/adaptive-icon.png`, `assets/splash.png`를 교체한다.
3. `app.config.ts`의 `splash.backgroundColor`를 새 배경색으로 맞춘다.
4. icon은 native 리소스라서 OTA update로 바뀌지 않는다. 새 store build가 필요하다.
5. development client도 다시 빌드해야 simulator에서 바뀐 icon이 보인다.

## Notes

- iOS는 투명 픽셀이 있는 icon을 거부한다. 업로드 전에 alpha channel을 지운다.
