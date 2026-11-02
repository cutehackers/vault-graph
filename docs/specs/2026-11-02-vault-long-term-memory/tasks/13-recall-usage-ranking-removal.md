## id

13

## title

[vault-graph] G2. 회상 순위에서 사용 기록을 빼고 `retired`를 반영한다

## goal

Graph Home의 사용 기록이 회상 순서를 바꾸지 않고, 폐기 페이지는 회상 목록에서 빠지고 알림 한 줄로만 나온다. spec Intent 1, 결정4를 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `src/vault_graph/context/pack/recall.py`
- `src/vault_graph/context/memory/project_memory.py` (`STALE_STATUSES`에 `retired`)
- `tests/test_session_recall.py`

## blockers

1, 4

작업 4를 선행으로 둔 이유: 이 작업은 계약2의 `retired`를 쓰고, A-23은 계약을 쓰는 G 커밋이 그 B 커밋보다 뒤이기를 요구한다.

## acceptance

A-9 (구획B), A-2 (구획C 알림 부분)

## checks

vault-graph worktree에서 실행한다.

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_session_recall.py tests/test_cli_hook_session_start.py`
- `grep -rn DEMOTE_AFTER_INJECTIONS src` (0건)
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [ ] 구획B는 모든 연결 Vault 페이지를 합쳐 `updated` 내림차순, 같으면 (Vault, 경로) 순이다
- [ ] "바뀐 항목 올리기"와 "열리지 않은 항목 내리기"가 지워졌고 `DEMOTE_AFTER_INJECTIONS`가 없다
- [ ] 사용 기록 네 경우(없음, 10회 주입 0회 열람, 내용 해시 변경, `usage/` 읽기 실패)에서 구획B 텍스트가 같다
- [ ] `retired`가 `NOTICE_STATUSES`에 있고 알림 줄이 "옛 제목 → 폐기됨: <retired_reason> (날짜)"다
- [ ] `injected`, `fetched` 기록은 계속 쓰고, 읽는 곳은 구획C 알림 중복 방지뿐이다

멈춤: 순위 제거에 `recall.py` 공개 시그니처 변경이 필요하면 보고한다.
