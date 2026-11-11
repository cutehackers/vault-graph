---
title: "Add a subcommand to gitcrumb"
summary: "Add a clap subcommand, its handler module, help text and tests."
tags: [gitcrumb, cli, rust]
---

# Add a subcommand to gitcrumb

## Steps

1. `crates/gitcrumb-cli/src/cli.rs`의 `Command` enum에 variant를 추가한다. doc comment가 `--help` 문구가 된다.
2. `crates/gitcrumb-cli/src/commands/<name>.rs`에 `pub fn run(args, ctx) -> Result<ExitCode>`를 만든다.
3. git을 다루는 로직은 `crates/gitcrumb-core`에 둔다. cli crate에는 출력 형식만 둔다.
4. `tests/cli_<name>.rs`에 fixture 저장소 기반 integration test를 추가한다.
5. `cargo run -- completions zsh > /dev/null`로 completion 생성이 깨지지 않는지 본다.
6. README의 명령 표에 한 줄을 추가한다.

## Notes

- exit code는 0 성공, 1 사용자 오류, 2 git 실패, 3 내부 오류로 정해져 있다.
