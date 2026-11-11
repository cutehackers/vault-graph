---
title: "Store crumbs in git notes"
summary: "gitcrumb writes crumbs to refs/notes/crumbs instead of a .gitcrumb sidecar file."
tags: [gitcrumb, cli, storage]
---

# Store crumbs in git notes

## Decision

gitcrumb는 crumb(commit에 붙이는 작업 메모)를 `refs/notes/crumbs` git notes에 저장한다. 저장소 안의 `.gitcrumb/` sidecar 파일은 쓰지 않는다.

## Why

- sidecar 파일은 commit을 따로 만들어야 하고, rebase 때 메모가 엉뚱한 commit을 가리키게 된다.
- git notes는 commit 내용을 바꾸지 않고 commit hash에 붙는다. `notes.rewriteRef` 설정으로 rebase·amend 뒤에도 따라간다.
- `git push origin refs/notes/crumbs`로 팀과 공유할 수 있다.

## Caveats

- GitHub 웹 화면은 notes를 보여주지 않는다. `gitcrumb export --format md`로 PR 설명에 붙인다.
- `gitcrumb doctor`가 `notes.rewriteRef` 설정 누락을 경고한다.
