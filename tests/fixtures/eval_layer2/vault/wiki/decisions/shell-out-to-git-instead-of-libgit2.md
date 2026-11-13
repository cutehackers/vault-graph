---
title: "Shell out to git instead of libgit2"
summary: "gitcrumb runs the git binary as a subprocess instead of linking libgit2 through the git2 crate."
tags: [gitcrumb, cli, rust, git]
---

# Shell out to git instead of libgit2

## Decision

gitcrumb는 `git` 실행 파일을 subprocess로 호출한다. git2 crate(libgit2 binding)는 제거한다. [[link-libgit2-through-the-git2-crate|Link libgit2 through the git2 crate]]를 대체한다.

## Why

- libgit2는 사용자의 git 설정(`includeIf`, credential helper, `core.fsmonitor`)을 일부만 따른다. 회사 저장소에서 notes push가 인증 실패했다.
- 정적 링크된 libgit2와 OpenSSL 때문에 macOS universal binary 빌드가 자주 깨졌다. 제거 후 binary 크기가 7.9MB에서 2.1MB로 줄었다.
- 사용자는 이미 git을 설치해 두었다. 같은 git이 같은 결과를 낸다.

## Trade-offs

- process 생성 비용이 있다. `trail` 명령은 `git log --format`과 `git notes list`를 한 번씩만 호출하도록 묶었다.
- git 2.30 미만은 지원하지 않는다. `gitcrumb doctor`가 버전을 확인한다.
