## id

9

## title

1차-3 `vg hook session-start` 세션 시작 회상과 `usage/` 사용 기록을 만든다 [수동 포함]

## goal

새 세션이 열리면 vg가 프로젝트 범위의 기억을 구획 A~D로 1,500토큰과 9,000자 안에 낸다. 회상할 수 없으면 종료 코드 3으로 넘겨 훅이 `recall.sh`를 쓰게 한다. spec Intent 3, 결정10, S3·S4·S11·S13을 다룬다.

## files

- `src/vault_graph/context/pack/recall.py` (새 파일: `recall()`, `RecallBundle`, 사용 기록 포트 Protocol)
- `src/vault_graph/storage/local/usage_log.py` (새 파일: `usage/` JSONL 덧붙이기와 읽기)
- `src/vault_graph/interface/cli/hook_commands.py` (새 파일)
- `src/vault_graph/interface/cli/main.py` (명령 등록)
- `src/vault_graph/interface/composition/read_only_service_factory.py` (벡터 저장소와 임베딩을 열지 않는 조립)
- `src/vault_graph/interface/mcp/mcp_resources.py` (페이지 읽기 성공 시 `fetched` 기록)
- `src/vault_graph/interface/mcp/mcp_service_factory.py`
- `src/vault_graph/context/memory/*` (날짜와 제목이 부족할 때만, spec 7절 7번)
- `tests/test_mcp_resource_read_only_boundary.py` (검사 기준을 "`usage/` 밖은 무변경"으로 바꿈)
- `tests/test_session_recall.py`
- `tests/test_cli_hook_session_start.py`
- `tests/test_usage_log.py`
- `tests/test_mcp_resource_usage_log.py`
- `tests/fixtures/session_recall/`

결정 (2026-10-30 승인): 새 파일 이름은 위와 같이 쓴다. `tests/test_mcp_resource_read_only_boundary.py`는 "`usage/` 밖은 무변경"으로 고쳐도 된다. A-15의 "바꾸지 않고 통과"는 MCP 도구 테스트에만 해당한다.

사람이 직접 하는 일: 실제 Vault에서 p95 측정, 사용자 범위 훅 임시 설정, 실제 Claude Code 세션 확인. vault-builder 저장소는 고치지 않는다. A-12의 "주입 대비 열린 비율"은 2주 운영 뒤 작업 14 보고서에 덧붙이는 후속 항목이며 이 작업의 완료 조건이 아니다.

## blockers

5, 7

## acceptance

A-10a, A-10b, A-10c, A-10d, A-10e, A-10f, A-10g, A-10h (수동), A-10i, A-11, A-12 (수동), A-20

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_session_recall.py tests/test_cli_hook_session_start.py tests/test_usage_log.py tests/test_mcp_resource_usage_log.py tests/test_mcp_resource_read_only_boundary.py tests/test_context_pack_read_only_boundary.py tests/test_feature_import_direction.py`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] `startup`, `clear`, `compact`, 모르는 값은 구획 A(비면 제목도 생략), B, C(해당 없으면 생략), D 순서로 내고, 토큰과 글자 두 한도를 모두 지킨다
- [ ] 구획B 줄 형식, 제외 상태, "추정"·"논쟁 중" 표시, 프로젝트 범위 밖 제외, frontmatter `type` 사용이 테스트된다
- [ ] 구획C가 사용 기록과 `superseded_by`로 "옛 제목 → 새 제목 (날짜)"를 내고, 사용 기록이 없으면 "최근 14일" 규칙을 쓴다
- [ ] `--max-tokens 300`이면 구획B가 줄고 "N개 생략"이 붙으며, 9,000자를 넘는 fixture에서는 글자 한도에서 멈춘다
- [ ] `resume`과 `fork`는 구획C만 내거나, 알릴 것이 없으면 빈 출력과 종료 코드 0으로 끝난다
- [ ] 넘김 상황마다 종료 코드가 정확히 3이고, 이때 `usage/`에 덧붙이지 않으며 Graph Home을 만들지 않는다. 예상하지 못한 예외는 0도 3도 아닌 코드다
- [ ] 실행 전후로 `usage/` 밖 Graph Home과 Vault의 바이트가 같다
- [ ] `usage/`를 쓰기 금지로 만들어도 결과와 종료 코드가 같고 표준 오류에 경고 한 줄이 있다. 리소스 읽기도 성공한다
- [ ] 임베딩 제공자나 벡터 저장소를 만들면 실패하는 대역으로도 통과한다
- [ ] (수동) 실제 Vault에서 연속 20회 실행의 p95가 2초 이하다
- [ ] (수동) 의존1이 없으므로 사람이 사용자 범위 훅을 임시로 설정하고, 새 세션의 `/context`, resume 시 무추가, vg를 PATH에서 뺀 경우의 `recall.sh` 넘김을 확인했다

## 작업2에서 넘어온 제약 (2026-10-30)

- `tests/test_feature_import_direction.py`는 M08(`context/pack/recall.py`)이 M17(`vault_map`)과 `storage/local`(`usage_log`)을 직접 가져오는 것을 막는다. M08 → M12도 DEP-04의 반대 방향이라 허용되지 않는다.
- 따라서 recall은 `vault-map` 조회와 사용 기록을 M08 또는 `storage/interfaces`에 정의한 Protocol로 주입받고, 구체 구현 연결은 composition에서 한다. spec 4.2.2의 "M12·M01이 쓰는 읽기 Protocol"과 별개로 recall용 Protocol을 둔다.
- M08 → M10은 허용된다(`STALE_STATUSES` 재사용).
