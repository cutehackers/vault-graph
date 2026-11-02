## id

18

## title

[vault-graph] G5. V4 구획A. `recall_pins.py`로 고정 기억을 세션 시작 회상 맨 앞에 넣는다

## goal

세션 시작 때 고정한 기억이 Vault와 상관없이 맨 앞에 400토큰 예산 안에서 들어온다. spec Intent 6, 결정14·S11을 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `src/vault_graph/context/pack/recall_pins.py` (새 파일, `pin_block(entries, *, max_tokens) -> PinBlock`)
- `src/vault_graph/context/pack/recall.py`
- `src/vault_graph/interface/cli/hook_commands.py` (위치 표기에 쓸 Vault 이름을 넘길 때만)
- `tests/test_recall_pins.py` (새 파일)
- `tests/test_session_recall.py`
- `tests/test_cli_hook_session_start.py`

## blockers

4, 13, 15

## acceptance

A-1 (단위 수준. 실제 Vault 증명은 작업 21), A-9 (구획A)

## checks

vault-graph worktree에서 실행한다.

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_recall_pins.py tests/test_session_recall.py tests/test_cli_hook_session_start.py tests/test_feature_import_direction.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [ ] `DocumentSnapshot.frontmatter`의 `pin`이 YAML 불리언 `true`일 때만 고정으로 보는 것을 테스트로 고정했다(위험6). 문자열 `"true"`는 구획B로 간다
- [ ] 구획A 제목이 `## 고정 기억`이고, 항목은 `- [m:<id>] <memory_kind 또는 type> · <제목> (<위치>)` 줄과 `summary` 줄 두 줄이다
- [ ] 순서는 `updated` 내림차순, 같으면 경로순이다
- [ ] 400토큰을 넘으면 뒤에서부터 줄이고 "N개 생략" 한 줄을 두며, 구획B 예산을 침범하지 않는다
- [ ] 구획A에 들어간 페이지는 구획B에 다시 나오지 않고, `retired`와 `STALE_STATUSES` 페이지는 구획A에 없다
- [ ] 모르는 `memory_schema` 값은 일반 페이지로 다루고 표준 오류에 경고 한 줄을 낸다
- [ ] 사용 기록 네 경우에서 구획A 텍스트가 같다
- [ ] Vault가 둘 이상이고 이름이 있으면 위치 표기에 이름을 쓴다

멈춤: Vault 이름을 넘기려면 `recall.py`의 공개 시그니처를 바꿔야 하면 보고한다.
