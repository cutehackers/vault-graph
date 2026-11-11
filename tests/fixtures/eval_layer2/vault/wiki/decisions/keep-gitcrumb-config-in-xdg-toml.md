---
title: "Keep gitcrumb config in XDG TOML"
summary: "gitcrumb reads user config from $XDG_CONFIG_HOME/gitcrumb/config.toml and repo config from git config."
tags: [gitcrumb, cli, config]
---

# Keep gitcrumb config in XDG TOML

## Decision

gitcrumb 사용자 설정은 `$XDG_CONFIG_HOME/gitcrumb/config.toml`(없으면 `~/.config/gitcrumb/config.toml`)에 둔다. 저장소별 설정은 `git config crumb.*` key로 둔다.

## Why

- macOS 기본 경로(`~/Library/Application Support`)는 dotfiles로 관리하기 불편하다. chezmoi로 관리하는 다른 도구와 같은 위치를 쓰고 싶었다.
- 저장소별 설정을 별도 파일로 두면 commit할지 말지 혼란이 생긴다. git config는 이미 사용자가 아는 방식이다.
- TOML은 Rust `serde`와 잘 맞고 주석을 쓸 수 있다.

## Precedence

명령행 flag > `git config crumb.*` > config.toml > 기본값.
