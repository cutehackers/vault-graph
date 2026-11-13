---
title: "Postgres RLS article notes"
summary: "Notes from an article on multi-tenant row-level security pitfalls."
tags: [ledgerline, postgres, source]
---

# Postgres RLS article notes

## Source

multi-tenant SaaS에서 RLS를 쓸 때의 함정을 다룬 블로그 글. Ledgerline RLS 도입 전에 읽었다.

## Takeaways

- table owner와 superuser는 RLS를 우회한다. 앱 role은 table owner가 아니어야 한다. `FORCE ROW LEVEL SECURITY`도 함께 켠다.
- connection pool에서 `SET`을 쓰면 다른 요청에 값이 남는다. `SET LOCAL`을 쓴다.
- policy 안의 함수 호출은 행마다 평가될 수 있다. `current_setting`은 괜찮지만 sub-select는 느리다.
- index는 `(org_id, ...)`로 시작하게 만든다.
