---
title: "Ship gitcrumb with cargo-dist and Homebrew"
summary: "gitcrumb binaries are built by cargo-dist and installed through a Homebrew tap."
tags: [gitcrumb, cli, release]
---

# Ship gitcrumb with cargo-dist and Homebrew

## Decision

gitcrumb 배포는 cargo-dist가 GitHub Release에 binary를 올리고, Homebrew tap(`brew install pebble-tools/tap/gitcrumb`)으로 설치하게 한다. crates.io 배포는 함께 하지만 기본 안내는 Homebrew다.

## Why

- `cargo install`은 Rust toolchain이 필요하고 빌드에 3분 걸린다. 사용자 대부분은 Rust 개발자가 아니다.
- cargo-dist는 macOS(arm64, x86_64), Linux(gnu, musl), Windows target과 shell installer, Homebrew formula를 한 설정으로 만든다.
- tag push 한 번으로 release가 끝난다.

## Not chosen

- 공식 homebrew-core 등록: 사용자 수 기준(GitHub star 75 이상)을 아직 못 넘는다.
