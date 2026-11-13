---
title: "Tidepool sync conflict rule"
summary: "Planned rule for merging intake logs from two devices: append-only logs, last-writer-wins settings."
tags: [tidepool, mobile, sync, draft]
---

# Tidepool sync conflict rule

## Status

v2 계획 단계의 규칙이다. v1에는 sync가 없다.

## Rule

- intake log는 append-only다. 각 기록은 기기에서 만든 UUIDv7 id를 가진다. 두 기기의 기록은 합집합으로 합친다. 삭제는 `deleted_at` tombstone으로 표시한다.
- 설정(목표량, 알림 간격)은 필드 단위 last-writer-wins다. 비교 기준은 기기 시계가 아니라 서버가 받은 시각이다.
- streak은 저장하지 않고 합쳐진 log로 다시 계산한다.

## Why not CRDT library

Automerge 같은 라이브러리는 이 정도 데이터 모양에 비해 무겁다. log가 append-only라서 단순 합집합으로 충분하다.
