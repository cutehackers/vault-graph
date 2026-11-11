---
title: "Manage Ledgerline changelog with release-please"
summary: "Ledgerline versions and CHANGELOG.md are produced by release-please from Conventional Commits."
tags: [ledgerline, backend, release]
---

# Manage Ledgerline changelog with release-please

## Decision

Ledgerline은 release-please GitHub Action으로 버전을 올리고 `CHANGELOG.md`를 만든다.

## Why

- 서버 배포는 main merge마다 일어나지만 고객에게 알릴 API 변경은 따로 묶어야 한다. release-please의 release PR이 그 묶음 역할을 한다.
- Conventional Commits(`feat:`, `fix:`)를 이미 쓰고 있어서 추가 작업이 없다.
- release PR을 merge하면 git tag와 GitHub Release가 함께 생긴다.

## Note

gitcrumb는 다른 방식(git-cliff)을 쓴다. [[generate-gitcrumb-changelog-with-git-cliff|Generate gitcrumb changelog with git-cliff]] 참고.
