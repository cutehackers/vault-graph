---
title: "Ledgerline tenant model"
summary: "Organizations, members, API keys and how org_id scopes every request."
tags: [ledgerline, backend, domain]
---

# Ledgerline tenant model

## Entities

- organization(`orgs`): 과금과 데이터 분리의 단위. 모든 tenant table이 `org_id`를 가진다.
- member(`org_members`): 대시보드에 로그인하는 사람. role은 `owner`, `admin`, `accountant`, `viewer`.
- API key(`api_keys`): 서버 간 호출용. 하나의 org에 묶이고 member에는 묶이지 않는다.

## Request scoping

1. middleware가 API key 또는 session cookie로 org를 찾는다.
2. transaction을 열고 `SET LOCAL app.org_id`를 설정한다.
3. handler 안의 모든 query는 RLS로 그 org 행만 본다.

한 사람이 여러 org에 속할 수 있다. 대시보드 상단의 org 전환기가 session의 현재 org를 바꾼다.
