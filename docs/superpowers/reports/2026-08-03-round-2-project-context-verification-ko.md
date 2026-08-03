# Round 2 프로젝트 컨텍스트 검증 보고서

작성일: 2026-08-03

## 결론

Round 2의 `explore_project` 경로는 코드와 Vault를 별도 권위로 유지한 채
하나의 읽기 전용 호출로 묶는다. 고정 Python/Dart/Vault fixture를 사용한
결정적 benchmark에서 네 가지 대표 작업 모두 기존 다중 도구 흐름보다
애플리케이션 호출 수와 프롬프트 지시 토큰이 줄었고, 필요한 증거 재현율은
낮아지지 않았으며 stale 결과 누락은 없었다.

이 검증은 LLM, 네트워크, 시간 측정에 의존하지 않는다. 따라서 CI와 오프라인
개발 환경에서 같은 입력에 같은 결과를 재현한다.

## 검증 fixture와 경계

`tests/fixtures/project_context/`는 다음을 함께 둔다.

- Python 계산 코드와 Dart 표시 코드
- 관련 Python 테스트 파일
- `project-vault`의 가격 계산 의사결정 문서
- `demo` 등록 코드 카탈로그와 `demo -> project-vault/wiki`의 명시적 binding
- 인덱스 이후 소스가 바뀐 `source_changed_since_index` stale 사례

fixture의 Vault와 repository 파일 트리 SHA-256 fingerprint를 호출 전후에
비교했다. benchmark와 코드 인덱스 미가용 fallback 모두 두 권위를 변경하지
않는다. fallback은 항상 Vault 증거만 반환하고 `code_index_unavailable` 경고를
포함하므로, 오래된 코드를 새 코드처럼 제시하지 않는다.

## Benchmark 결과

토큰은 직렬화된 응답 및 고정 지시문 길이에서 계산한 결정적 추정치다. 출력
상한은 1,200 tokens, depth=2, limit=20이다.

| 시나리오 | 기존 호출 → 탐색 호출 | 지시 토큰 → 탐색 토큰 | fallback 읽기 → 탐색 읽기 | 증거 재현율 | stale 누락 | 탐색 출력 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 구조 설명 | 4 → 1 | 40 → 15 | 3 → 0 | 1.00 | 0 | 762 |
| 버그 범위 | 5 → 1 | 46 → 15 | 4 → 0 | 1.00 | 0 | 1,039 |
| 영향 분석 | 5 → 1 | 32 → 15 | 4 → 0 | 1.00 | 0 | 935 |
| 설계·구현 일관성 | 5 → 1 | 45 → 15 | 4 → 0 | 1.00 | 0 | 765 |

각 시나리오에서 다음 acceptance threshold를 만족한다.

- `explore_project` 애플리케이션 호출 수가 scripted baseline보다 작다.
- 프롬프트 지시 토큰이 baseline보다 작다.
- 관련 증거 재현율이 baseline(1.00) 이상이다.
- stale 결과 누락은 정확히 0이다.
- MCP 출력은 max token/depth/limit 경계 안에 있다.
- Vault와 repository fingerprint가 호출 전후 동일하다.
- 코드 인덱스 미가용 fallback은 두 호출에서 동일하게 직렬화된다.

## 제품 계약 확인

- Vault는 지속 지식의 권위이고, 등록 repository는 현재 실행 코드의 권위다.
- `ProjectBinding`은 Graph state에만 저장되며 active Vault나 작업 디렉터리를
  추측하지 않는다.
- `explore_project`는 `ProjectContextService`만 호출한다. MCP 어댑터는 SQLite를
  열거나 repository 파일을 직접 읽지 않는다.
- 코드 증거는 검증된 `vg-source://` line URI만 제공하며, source body와 절대 경로를
  직렬화하지 않는다.
- harness guidance 쓰기는 사용자가 명시적으로 선택한 Vault 밖의
  `AGENTS.md`/`CLAUDE.md`에만 적용된다. MCP 시작과 일반 탐색은 쓰지 않는다.

기존 `docs/DECISIONS.md`의 2026-07-30 통합 프로젝트 증거 계층 결정으로 이
계약은 이미 승인되어 있다. 이번 검증은 새 제품 결정을 추가하지 않았으므로
`DECISIONS.md`는 변경하지 않았다.

## 실행한 검증 게이트

최종 실행 결과는 아래와 같다.

```text
uv run pytest tests/benchmarks/test_project_context_benchmark.py tests/test_project_context_serialization.py -q
7 passed

uv run pytest -q
1122 passed, 1 skipped

uv run ruff check .
All checks passed

uv run ruff format --check tests/benchmarks/test_project_context_benchmark.py tests/test_project_context_serialization.py
2 files already formatted

uv run mypy src tests
Success: no issues found

uv build
source distribution and wheel built

uv lock --check
lock is valid

git diff --check
no whitespace errors

VG_RUN_MCP_STDIO_SMOKE=1 uv run pytest tests/test_mcp_stdio_smoke.py -q
1 passed (stdio gate enabled)
```

`VG_RUN_MCP_STDIO_SMOKE`는 의도적으로 활성화한다. `mcp` runtime이 설치되어
있는 환경에서는 skip이 아니라 실제 stdio protocol smoke를 실행해야 하며,
실행 가능한 환경에서 실패하면 Round 2 완료를 막는다.
