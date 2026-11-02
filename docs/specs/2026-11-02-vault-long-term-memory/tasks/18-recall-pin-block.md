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

- [x] `DocumentSnapshot.frontmatter`의 `pin`이 YAML 불리언 `true`일 때만 고정으로 보는 것을 테스트로 고정했다(위험6). 문자열 `"true"`는 구획B로 간다
- [x] 구획A 제목이 `## 고정 기억`이고, 항목은 `- [m:<id>] <memory_kind 또는 type> · <제목> (<위치>)` 줄과 `summary` 줄 두 줄이다
- [x] 순서는 `updated` 내림차순, 같으면 경로순이다
- [x] 400토큰을 넘으면 뒤에서부터 줄이고 "N개 생략" 한 줄을 두며, 구획B 예산을 침범하지 않는다
- [x] 구획A에 들어간 페이지는 구획B에 다시 나오지 않고, `retired`와 `STALE_STATUSES` 페이지는 구획A에 없다
- [x] 모르는 `memory_schema` 값은 일반 페이지로 다루고 표준 오류에 경고 한 줄을 낸다
- [x] 사용 기록 네 경우에서 구획A 텍스트가 같다
- [x] Vault가 둘 이상이고 이름이 있으면 위치 표기에 이름을 쓴다

멈춤: Vault 이름을 넘기려면 `recall.py`의 공개 시그니처를 바꿔야 하면 보고한다.

멈춤 판단 (2026-11-02, 오케스트레이터): Vault 이름을 넘기려면 `RecallScope`에 기본값이 있는 선택 필드 `vault_names`를 더해야 한다. 기존 호출자는 바뀌지 않으므로 SPEC §5 호환 규칙("선택 필드는 더할 수 있다")에 맞는 더하기로 보고 멈추지 않았다. 옵션1을 골랐다: `_ProjectRecallScope.resolve`에서 `vault_labels`로 채우며, 이를 위해 `read_only_service_factory.py`를 범위에 더했다.

기록 (2026-11-02): 집중 테스트 4개 파일 128개 통과. Vault가 둘 이상이면 위치에 map 이름을 쓰고, 구획D에 `이름=vault_id` 대응을 적는다. 구획B 날짜 동률은 (Vault 이름, 경로)로 푼다(V4). 고정 기억이 보였던 실행도 알림 기록에 넣어, 보였던 고정 기억이 폐기되면 알림이 나온다. 전체 pytest는 작업 17 커밋 뒤 함께 확인한다.
