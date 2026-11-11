---
title: "gitcrumb crate layout"
summary: "The gitcrumb workspace has a core crate for git and notes logic and a cli crate for output."
tags: [gitcrumb, cli, architecture]
---

# gitcrumb crate layout

## Crates

- `crates/gitcrumb-core`: git subprocess 실행(`git::Runner`), notes 읽기/쓰기, crumb 파싱, trail 계산. 출력 형식을 모른다.
- `crates/gitcrumb-cli`: clap 정의, 명령 handler, 사람용 출력(`owo-colors`)과 `--json` 출력.
- `xtask`: completion과 man page 생성(`cargo xtask dist-assets`).

## Boundaries

- core는 `std::process::Command`를 직접 부르지 않고 `git::Runner` trait을 거친다. test에서 가짜 runner를 넣는다.
- cli는 git 명령 문자열을 만들지 않는다.
