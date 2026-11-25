# 4. SPEC, 정규화 계약, ARCHITECTURE를 고치고 실제 Vault 이전을 main 세션에 넘긴다

## id
4

## title
SPEC, 정규화 계약, ARCHITECTURE를 고치고 실제 Vault 이전을 main 세션에 넘긴다

## goal
새 명령과 파일이 문서에 있어 다음 사람이 규칙을 찾을 수 있다. 끝 조건과 실제 이전 순서는 이 task가 코드로 만들지 않고 main 세션이 구현 뒤 돌리도록 정리해 둔다.

## units
- D11
- A10
- D1
- D12
- A11
- A12

## files
- docs/SPEC.md
- docs/contracts/vg-session-jsonl-v1.md
- docs/ARCHITECTURE.md

## blockers
3

## checks
- 수동: `docs/SPEC.md`의 `vg session export` 줄 근처, `docs/contracts/vg-session-jsonl-v1.md` §4, `docs/ARCHITECTURE.md` §1 파일 표와 §4 세션 수집 행에서 `vg session migrate`, `v1_coverage.py`, `session_migration.py`를 찾는다 (A10)
- 수동: 구현 검증 뒤 main 세션이 `vg session migrate --dry-run`, `vg session migrate`, 다시 `vg session migrate --dry-run`을 돌리고 마지막 출력의 Vault 요약 줄을 본다 (A11)
- 수동: 실행 보고 시각이 3b~3e 구현 commit보다 앞서는지 git log와 보고로 확인한다 (A12)

## done-when
- [ ] SPEC에 `vg session migrate` 한 줄이 `vg session export` 옆에 있다
- [ ] 계약 §4에 명령 형식, 덮음 규칙, 끝난 세션 정규화와 1시간 규칙, 출력, 종료 코드가 있다
- [ ] ARCHITECTURE §1 파일 표(M19 행 포함)와 §4 세션 수집 행에 `v1_coverage.py`, `session_migration.py`, 새 명령이 있다
- [ ] AGENTS.md는 바뀌지 않았다
- [ ] D1, D12, A11, A12는 코드 작업이 아니다. main 세션이 구현 검증 뒤 실행하고, 이 task는 코드 변경 없이 이 항목을 사용자 보고 대상으로 남긴다
