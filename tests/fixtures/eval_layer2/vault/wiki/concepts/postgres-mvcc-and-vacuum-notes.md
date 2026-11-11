---
title: "Postgres MVCC and vacuum notes"
summary: "Personal study notes on MVCC, dead tuples and autovacuum tuning."
tags: [personal, postgres, study]
---

# Postgres MVCC and vacuum notes

## MVCC

UPDATE는 기존 행을 고치지 않고 새 버전(tuple)을 만든다. 옛 버전은 dead tuple로 남고 VACUUM이 치운다.

## Why it matters for queues

River 같은 Postgres queue는 job 행을 자주 UPDATE한다. dead tuple이 쌓이면 index scan이 느려진다.
`river_job` table은 `autovacuum_vacuum_scale_factor = 0.01`로 낮춰서 더 자주 vacuum하게 했다(Ledgerline).

## Checks

- `pg_stat_user_tables.n_dead_tup`과 `last_autovacuum`을 본다.
- long-running transaction이 있으면 vacuum이 dead tuple을 못 치운다. `pg_stat_activity`의 `xact_start`를 확인한다.
