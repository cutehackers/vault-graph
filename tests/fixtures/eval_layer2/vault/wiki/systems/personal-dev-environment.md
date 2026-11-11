---
title: "Personal dev environment"
summary: "Shell, editor and runtime tooling on my machines: zsh, Neovim, WezTerm and mise."
tags: [personal, dotfiles, tools]
---

# Personal dev environment

## Tools

- shell: zsh + starship prompt. plugin manager 없이 `zsh-autosuggestions`만 직접 source한다.
- terminal: WezTerm. 설정은 `~/.config/wezterm/wezterm.lua`.
- editor: Neovim(LazyVim 기반) + VS Code(디버깅용).
- runtime 버전: mise(`~/.config/mise/config.toml`). asdf에서 2026-03에 옮겼다.
- git: delta pager, `gh` CLI, 개인 스크립트 `wt-new`, `wt-clean`.

## Locations

개인 스크립트는 `~/.local/bin`. chezmoi source는 `~/.local/share/chezmoi`.
