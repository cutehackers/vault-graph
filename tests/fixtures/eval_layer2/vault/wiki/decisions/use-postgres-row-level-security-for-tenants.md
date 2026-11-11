---
title: "Use Postgres row-level security for tenants"
summary: "Ledgerline isolates tenant data with Postgres RLS policies on every tenant table."
tags: [ledgerline, backend, postgres, security]
---

# Use Postgres row-level security for tenants

## Decision

Ledgerline API는 tenant(organization) 분리를 Postgres row-level security(RLS)로 강제한다. 모든 tenant table에 `org_id` column과 RLS policy를 둔다.

## Why

- 애플리케이션 코드의 `WHERE org_id = $1` 누락 한 번이 다른 회사 invoice 노출로 이어진다. 2026-04 code review에서 실제로 누락이 한 건 발견됐다.
- RLS는 DB가 마지막 방어선이 된다. query를 잘못 써도 다른 tenant 행이 보이지 않는다.
- schema-per-tenant는 migration을 tenant 수만큼 돌려야 해서 운영 부담이 크다.

## How it works

- request마다 transaction 시작 시 `SET LOCAL app.org_id = '<uuid>'`를 실행한다.
- policy는 `USING (org_id = current_setting('app.org_id')::uuid)`이다.
- migration과 batch job은 `BYPASSRLS` role인 `ledgerline_admin`으로 돈다.
