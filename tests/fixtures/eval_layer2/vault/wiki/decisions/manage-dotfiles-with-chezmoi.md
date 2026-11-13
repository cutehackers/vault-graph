---
title: "Manage dotfiles with chezmoi"
summary: "Personal dotfiles moved from GNU stow symlinks to chezmoi templates."
tags: [personal, dotfiles]
---

# Manage dotfiles with chezmoi

## Decision

개인 dotfiles는 chezmoi로 관리한다. GNU stow symlink 방식은 그만둔다.

## Why

- 회사 노트북과 개인 Mac mini의 git email, ssh 설정이 달라야 한다. chezmoi template(`{{ if eq .chezmoi.hostname "mini" }}`)으로 한 저장소에서 처리된다.
- API token 같은 비밀값을 1Password CLI(`onepasswordRead`)로 가져올 수 있다. stow 때는 `.zshrc.local`을 손으로 복사했다.
- 새 기기에서 `chezmoi init --apply <repo>` 한 줄로 끝난다.

## Trade-off

파일을 직접 수정하면 chezmoi source와 어긋난다. 수정은 항상 `chezmoi edit`으로 한다.
