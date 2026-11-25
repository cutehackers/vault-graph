# 등록 Vault의 v1 part와 시험 수집 결과

측정일: 2026-11-25. 측정은 이 change를 맡긴 상위 세션이 했고 brief `조사 결과`에 적었다. vault-graph Vault의 v1 part 수는 이 spec을 쓰며 다시 셌다(X11). Vault 목록은 `vault-map.json` 기준이다.

### X12. 등록 Vault 다섯 곳에 v1 part가 89개 있다
- source: brief 조사 결과(2026-11-25 측정), vault-graph 값은 X11에서 다시 셈
- basis: X11

| Vault | 전체 part | v1 part | v1 세션 |
|---|---|---|---|
| vault-graph | 79 | 36 | 23 |
| 981park-flutter-app | 39 | 1 | 1 |
| bake | 30 | 9 | 6 |
| sgp-981-app | 136 | 30 | 20 |
| vault-builder | 19 | 13 | 5 |

personal Vault에는 `raw/sessions`가 없다. 상위 spec이 적은 35개는 이날 36개다.

### X13. v1 part 뒤에 v2 part가 이어진 세션이 있다
- source: brief 조사 결과(2026-11-25 측정)

vault-graph `ae647dc5`는 part1~7이 v1, part8~10이 v2다. sgp-981-app의 `2be25576`, `a7ee713f`, `d477aed9`, `e6fdf1b4`도 같은 모양이다. 뒤의 v2 part는 커서 다음부터 썼으므로 앞 v1 part의 시간 범위를 담지 않는다.

### X14. bake Vault의 두 세션은 원본 jsonl이 없다
- source: brief 조사 결과(2026-11-25 측정)

bake Vault의 v1 세션 6개 중 `d353dbe2`, `d4e0c1e8`은 `~/.claude/projects/` 아래에 원본이 없다. 이 두 세션의 v1 part는 다시 수집할 수 없다.

### X15. 가장 오래된 원본 jsonl의 수정 시각은 2026-10-22다
- source: brief 조사 결과(2026-11-25 측정)

Claude Code는 기본 30일 뒤 원본을 지운다. 10월 말 원본은 언제든 지워질 수 있다.

### X16. Vault 복사본 시험에서 15세션은 교환 수가 맞게 써졌다
- source: brief 조사 결과(2026-11-25, Vault 복사본에 vault-graph 23세션을 `--rerender`로 수집)

실제 Vault가 아닌 scratch 복사본에서 시험했다. 15세션은 `written`이었고 `exchange_count`가 정규화 파일의 "턴 있는 닫힌 교환 수"와 같았다.

### X17. cwd가 지금 없는 worktree인 7세션은 Vault가 쓰지 않았다
- source: brief 조사 결과(같은 시험)

세션 cwd가 지금은 없는 `.worktrees/feat-jh-local-graph` 같은 폴더라, Vault 도구가 "is not inside a git repository. Nothing written."으로 건너뛰었다.

### X18. 프로젝트 폴더의 가장 최근 세션은 교환이 열린 채 정규화되어 일부만 써졌다
- source: brief 조사 결과(같은 시험)
- basis: X4, X9

`08c6f4d5`는 그 폴더의 가장 최근 세션이라 교환 하나가 열려 10개 중 7개만 써졌다. `3613510c`(열린 main 1개와 열린 subagent 72개), `659a1bac`(열린 교환 1개)도 같은 원인이다.

### X19. 끝난 세션 정규화와 상위 폴더 cwd로 Vault 다섯 곳 복사본에 시험하면 원본 있는 53세션이 모두 맞게 써진다
- source: 2026-11-25 scratch 시험. 등록 Vault 다섯 곳을 scratch로 복사하고, 복사본을 가리키는 `vault-map.json`을 `CLAUDE_CONFIG_DIR`로 넘겨 각 복사본의 `tools/wiki/cli.py sessions capture --json --normalized F --rerender --trigger SessionEnd --cwd C`를 돌렸다. 정규화는 `ClaudeCodeSession(newest=False)`로 했고, `C`는 세션 cwd가 없으면 가장 가까운 존재하는 상위 폴더다. 실제 Vault는 건드리지 않았다.
- basis: X4, X9, X17, X18

원본 있는 53세션(vault-graph 23, 981park-flutter-app 1, bake 4, sgp-981-app 20, vault-builder 5)이 모두 `written`이었다. 결과 `vault`는 v1 part가 있던 Vault와 모두 같았고, `exchange_count`는 정규화 파일의 "턴이 하나 이상인 교환 수"와 모두 같았다. 그중 30세션은 cwd가 지금 없는 폴더라 상위 폴더를 넘겼다. X18의 세 세션도 모든 교환이 써졌다(08c6f4d5 10개, 3613510c 119개, 659a1bac 1개). 원본 없는 bake 두 세션은 돌리지 않았다.

### X20. v2 frontmatter `last_turn_at`은 가장 늦은 시각이 아니다. 교환 메타의 `started`·`ended` 범위로 보면 모든 v1 part가 덮인다
- source: X19 시험 뒤 복사본의 part 머리와 본문을 다시 읽어 잼(2026-11-25)
- basis: X11, X19

v2 part의 `last_turn_at`은 파일 순서상 마지막 턴의 시각이다. main 교환 뒤에 subagent 교환이 붙으므로 그 시각이 main 마지막 턴보다 이를 수 있다(예: vault-graph 6b689ea0 v2 `last_turn_at` 10:59:02, v1 `last_turn_at` 11:02:59). 그래서 frontmatter 시각만으로 덮음을 보면 시험 뒤에도 Vault 넷에서 원본 있는 세션의 v1 part 43개가 덮이지 않은 것으로 나온다. v2 본문의 `<!-- vg:exchange ... started=… ended=… -->` 줄에서 가장 이른 `started`와 가장 늦은 `ended`를 범위로 쓰면, 원본 있는 세션의 v1 part는 다섯 곳 모두 덮이고 남는 것은 원본 없는 bake 두 part뿐이다.
