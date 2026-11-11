---
title: "River queue documentation notes"
summary: "Notes from the River docs on transactional enqueue, unique jobs and the cleaner."
tags: [ledgerline, jobs, source]
---

# River queue documentation notes

## Source

River(riverqueue.com) 공식 문서.

## Notes

- `InsertTx`로 비즈니스 transaction 안에서 job을 넣는다. commit되지 않으면 job도 없다.
- unique job: `UniqueOpts{ByArgs: true, ByPeriod: time.Hour}`로 같은 인자의 job을 한 시간에 하나만 넣는다. 정기 청구 job에 썼다.
- 완료 job은 cleaner가 기본 24시간 뒤 지운다. Ledgerline은 7일로 늘렸다.
- `riverui`는 별도 binary다. 내부망에서만 띄운다.
