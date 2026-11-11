---
title: "Debug gitcrumb with verbose tracing"
summary: "Turn on tracing output and print the git commands gitcrumb runs."
tags: [gitcrumb, cli, debugging]
---

# Debug gitcrumb with verbose tracing

## Steps

1. `GITCRUMB_LOG=debug gitcrumb trail`로 실행하면 실행하는 git 명령과 걸린 시간이 stderr에 나온다. `RUST_LOG`가 아니라 `GITCRUMB_LOG`이다.
2. 더 자세히 보려면 `GITCRUMB_LOG=gitcrumb=trace`.
3. `-vv` flag는 `GITCRUMB_LOG=debug`와 같다.
4. git 쪽 문제로 보이면 `GIT_TRACE=1`을 함께 켠다.
5. 사용자에게 bug report를 받을 때는 `gitcrumb doctor --json` 출력을 함께 받는다.

## Notes

- trace 출력에 원격 URL이 나온다. token이 URL에 들어간 저장소라면 공유 전에 지운다.
