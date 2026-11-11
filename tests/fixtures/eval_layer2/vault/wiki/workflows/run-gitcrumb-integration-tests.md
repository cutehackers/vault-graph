---
title: "Run gitcrumb integration tests"
summary: "Run the fixture-repository integration tests with cargo nextest."
tags: [gitcrumb, cli, testing]
---

# Run gitcrumb integration tests

## Steps

1. `cargo nextest run --profile ci`로 unit test와 integration test를 함께 돌린다.
2. integration test는 `tests/fixtures/*.sh` 스크립트로 임시 git 저장소를 만든다. 스크립트가 `GIT_AUTHOR_DATE`를 고정해서 commit hash가 매번 같다.
3. snapshot test는 `insta`를 쓴다. 출력이 바뀌었으면 `cargo insta review`로 확인하고 승인한다.
4. git 버전 차이를 보려면 `GITCRUMB_GIT=/opt/git-2.30/bin/git cargo nextest run`으로 옛 git을 지정한다.

## Notes

- macOS에서 `/tmp`가 symlink라서 경로 snapshot이 달라질 수 있다. test helper가 `canonicalize`로 맞춘다.
