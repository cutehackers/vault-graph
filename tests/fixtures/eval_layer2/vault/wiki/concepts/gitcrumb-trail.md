---
title: "gitcrumb trail"
summary: "A trail is the ordered list of crumbs along a branch since it left its base."
tags: [gitcrumb, cli, domain]
---

# gitcrumb trail

## Definition

trail은 현재 branch가 base branch에서 갈라진 뒤의 commit들에 붙은 crumb을 시간 순서로 늘어놓은 것이다. base는 `crumb.base` git config, 없으면 `origin/HEAD`다.

## Use

- PR을 열기 전에 `gitcrumb trail`로 남은 `todo`를 확인한다.
- `gitcrumb trail --kind todo --open`은 아직 `done:` 표시가 없는 todo만 보여준다.
- `gitcrumb export --format md`는 trail을 PR 설명용 markdown으로 바꾼다.

## Note

rebase로 commit hash가 바뀌어도 `notes.rewriteRef`가 설정돼 있으면 trail은 유지된다.
