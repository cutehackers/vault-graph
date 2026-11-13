---
title: "cargo-dist documentation notes"
summary: "Notes from the cargo-dist docs about targets, installers and the Homebrew publish job."
tags: [gitcrumb, release, source]
---

# cargo-dist documentation notes

## Source

cargo-dist(dist) 공식 문서.

## Notes

- `cargo dist init`이 `[workspace.metadata.dist]` 설정과 `.github/workflows/release.yml`을 만든다.
- installers = `["shell", "homebrew"]`. homebrew는 `tap = "pebble-tools/homebrew-tap"`과 `HOMEBREW_TAP_TOKEN` secret이 필요하다.
- `cargo dist plan`은 실제 빌드 없이 artifact 목록을 보여준다.
- 설정을 바꾸면 `cargo dist generate`로 workflow 파일을 다시 만든다. 직접 고치면 다음 generate에서 덮인다.
