---
title: "Link libgit2 through the git2 crate"
summary: "Superseded. gitcrumb 0.1 linked libgit2 through the git2 crate."
tags: [gitcrumb, cli, rust, git, superseded]
---

# Link libgit2 through the git2 crate

> Status: superseded by [[shell-out-to-git-instead-of-libgit2|Shell out to git instead of libgit2]] (gitcrumb 0.4).

## Decision (old)

gitcrumb 0.1~0.3은 git2 crate로 libgit2를 링크해서 git 저장소를 읽고 notes를 썼다.

## Why (at the time)

- subprocess 출력 파싱 없이 typed API로 commit과 notes를 다룰 수 있었다.
- Windows에서 git 실행 파일 경로를 찾는 문제를 피할 수 있다고 봤다.

## Why it was reversed

credential helper와 `includeIf` 미지원, 빌드 크기, OpenSSL 링크 문제가 typed API의 장점보다 컸다.
