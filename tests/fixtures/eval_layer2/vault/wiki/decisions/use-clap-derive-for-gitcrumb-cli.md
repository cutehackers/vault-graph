---
title: "Use clap derive for gitcrumb CLI"
summary: "gitcrumb parses arguments with clap's derive API."
tags: [gitcrumb, cli, rust]
---

# Use clap derive for gitcrumb CLI

## Decision

gitcrumb의 명령행 인자는 clap 4의 derive API(`#[derive(Parser)]`)로 정의한다. builder API는 쓰지 않는다.

## Why

- subcommand가 `add`, `show`, `trail`, `export`, `doctor`로 늘어나면서 builder 코드가 400줄을 넘었다. derive는 struct 정의가 곧 문서다.
- `--help` 문구를 doc comment에서 가져와서 코드와 도움말이 어긋나지 않는다.
- `clap_complete`로 zsh/fish completion을 같은 정의에서 만든다.

## Alternatives

- `argh`: 작고 빠르지만 completion 생성이 없다.
- `lexopt`: 의존성이 거의 없지만 subcommand 많은 CLI에서는 코드가 길어진다.
