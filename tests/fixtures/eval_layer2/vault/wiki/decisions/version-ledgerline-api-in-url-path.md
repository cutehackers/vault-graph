---
title: "Version Ledgerline API in the URL path"
summary: "Public API versions are part of the path (/v1/), not a header."
tags: [ledgerline, backend, api]
---

# Version Ledgerline API in the URL path

## Decision

Ledgerline public API의 버전은 URL path에 넣는다(`/v1/invoices`). `Accept-Version` header 방식은 쓰지 않는다.

## Why

- 고객사 개발자 다수가 curl과 Postman으로 먼저 시험한다. path에 버전이 있어야 문서 예시를 그대로 붙여넣어 쓸 수 있다.
- CDN과 log에서 버전별 트래픽을 path만으로 나눌 수 있다.
- header 방식은 고객이 header를 빠뜨리면 어떤 버전으로 응답할지 정책이 또 필요하다.

## Rules

- 하위 호환이 깨지는 변경만 `/v2/`를 만든다. 필드 추가는 같은 버전 안에서 한다.
- 옛 버전은 공지 후 최소 12개월 유지한다.
