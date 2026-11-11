---
title: "Trace Ledgerline with OpenTelemetry"
summary: "Ledgerline sends traces through OpenTelemetry to Grafana Tempo instead of Sentry performance."
tags: [ledgerline, backend, observability]
---

# Trace Ledgerline with OpenTelemetry

## Decision

Ledgerline은 request trace를 OpenTelemetry SDK로 만들고 Grafana Cloud의 Tempo로 보낸다. Sentry는 error 수집에만 쓰고 performance monitoring은 끈다.

## Why

- River job과 HTTP request를 한 trace로 이어 보고 싶었다. Sentry performance는 Go background job 지원이 약했다.
- Grafana Cloud 무료 tier에 log(Loki), metric, trace가 함께 있어서 한 화면에서 본다.
- vendor를 바꿔도 OTel exporter만 바꾸면 된다.

## Note

Tidepool(모바일)은 Sentry를 계속 쓴다. 이 결정은 Ledgerline 서버에만 해당한다.
