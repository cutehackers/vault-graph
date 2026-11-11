---
title: "Cut a gitcrumb release"
summary: "Bump the version, generate the changelog, tag, and let cargo-dist publish binaries."
tags: [gitcrumb, cli, release]
---

# Cut a gitcrumb release

## Steps

1. `cargo set-version 0.X.Y`로 `Cargo.toml` 버전을 올린다(cargo-edit 필요).
2. `git cliff --tag v0.X.Y -o CHANGELOG.md`로 changelog를 만든다. 내용을 읽고 어색한 문장을 고친다.
3. `cargo dist plan`으로 만들어질 artifact 목록을 확인한다.
4. `chore(release): v0.X.Y`로 commit하고 `git tag v0.X.Y`를 만든다.
5. `git push origin main --tags`. tag push가 cargo-dist의 `release.yml` workflow를 시작한다.
6. workflow가 끝나면 GitHub Release와 `pebble-tools/homebrew-tap`의 formula가 갱신된다.
7. `cargo publish`로 crates.io에도 올린다. 이건 수동이다.

## Notes

- tag를 잘못 만들었으면 release workflow가 끝나기 전에 tag를 지우고 Release draft도 지운다.
