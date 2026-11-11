---
title: "gitcrumb crumb"
summary: "A crumb is a short work note attached to a commit through git notes."
tags: [gitcrumb, cli, domain]
---

# gitcrumb crumb

## Definition

crumb은 commit 하나에 붙이는 짧은 작업 메모다. 왜 이렇게 바꿨는지, 다음에 무엇을 해야 하는지, 어떤 명령을 돌렸는지를 남긴다. commit message에 넣기에는 사적이거나 임시적인 내용이 대상이다.

## Format

notes 내용은 한 줄에 crumb 하나, `<kind>: <text>` 형식이다. kind는 `why`, `todo`, `ran`, `link` 네 가지다.

```
why: retry 간격을 늘려서 rate limit을 피함
todo: backoff 상한을 config로 빼기
```

## Commands

`gitcrumb add todo "..."`가 HEAD에 붙인다. `--commit <rev>`로 다른 commit을 지정한다.
