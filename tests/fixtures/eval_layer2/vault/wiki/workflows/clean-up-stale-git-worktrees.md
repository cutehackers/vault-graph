---
title: "Clean up stale git worktrees"
summary: "Remove merged worktrees and prune dangling worktree metadata with the wt-clean script."
tags: [personal, git, tools]
---

# Clean up stale git worktrees

## Steps

1. `wt-clean --dry-run`으로 지울 worktree 목록을 본다. 기준은 branch가 `origin/main`에 merge됐고 작업 트리에 변경이 없는 것이다.
2. 목록이 맞으면 `wt-clean`을 실행한다. 각 worktree에 `git worktree remove`를 실행하고 local branch도 지운다.
3. 폴더를 손으로 지운 경우가 있으면 `git worktree prune`으로 남은 metadata를 정리한다.
4. 변경이 남은 worktree는 건너뛰고 경로를 출력한다. 직접 확인한다.

## Notes

- `wt-clean`은 `~/.local/bin/wt-clean`에 있는 개인 zsh 스크립트다. chezmoi가 관리한다.
- squash merge된 branch는 merge 판정이 안 된다. `--squash-aware` flag가 `gh pr list --state merged`로 확인한다.
