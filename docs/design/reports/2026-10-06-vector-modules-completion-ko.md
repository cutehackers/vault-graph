# 2차 리팩터링 완료 보고서

기준 커밋: `aa130b6`. 대상: 범용 임베딩·벡터 저장/검색·증분 인덱싱과 Vault 연동 계층. 기능 계약은 [명세](../specs/2026-10-06-vector-modules-ko.md)에 정의한다.

## 구현

- `packages/text-embeddings`: `nolemy-text-embeddings`, 일반 입력·모델·벡터 계약과 선택적인 FastEmbed 제공자. 모델은 명시한 로컬 경로나 구성된 백엔드로만 사용한다.
- `packages/vector-search`: `nolemy-vector-search`, 불투명한 메타데이터를 사용하는 Chroma 저장·검색·삭제·목록·상태와 읽기 전용 SQLite 조회. Chroma SDK는 선택 의존성이다.
- `packages/vector-index`: `nolemy-vector-index`, 논리적 범위의 전체 목록/부분 변경 계획, 배치 검증·실행과 Chroma 연결용 코덱. 실행은 현재 목록으로 계획을 재검증한다.
- `src/vault_graph/vault_adapter`: 기존 텍스트 준비·ID·범위·리비전·저장 형식과 오류를 유지하는 연동 구현. 기존 가져오기 경로는 호환 진입점이다. 기존 상태·근거 조회·세대 발행 경로는 새 모듈을 이용한다.
- 루트 의존성·잠금 파일·CI/배포 워크플로와 독립 설치 검증기를 갱신했다. 커밋·업로드·푸시는 수행하지 않았다.

## 완료 조건과 증거

1. **독립 실행:** `tests/verify_graph_module_wheels.py`는 작업 공간 밖에 새 환경을 만들고 임베딩, 벡터 검색의 선택 의존성 분리, 텍스트→색인→실제 Chroma 검색·읽기 전용 재개방을 실행했다. Vault·그래프 패키지 미설치를 확인했다.
2. **Vault 호환:** 기존 전체 테스트를 유지했다. CLI/MCP/HTTP 결과·필터·점수·근거·리비전·읽기 전용·발행 실패 복구를 포함해 1,352개 통과, 조건부 legacy MCP stdio smoke 1개 생략이다. 기존 Starlette/httpx 사용 중단 안내 1개가 남는다.
3. **갱신 안전성:** 새 공개 테스트는 전체/부분 입력, 빈 입력, 이전 모델 정리, 동일 ID의 논리 범위 분리, 잘못된/오래된 계획 거부, 배치 출력 오류, 비정상 벡터 값, 부분 저장 실패 후 새 계획 재시도를 검증한다.
4. **저장 안전성:** 읽기 전용 파일 해시, 조건이 맞지 않는 삭제의 payload 보존, 복사된 메타데이터의 실제 저장 ID 확인, SDK 쓰기 전 호환성 검사, 컬렉션별 legacy queue 조회를 검증한다.
5. **정적 검사:** Ruff 전체 검사·변경 파일 포맷, 루트/테스트/새 패키지 전체 mypy(364개 파일), 새 패키지별 독립 strict mypy, 잠금 파일 검사와 diff 공백 검사가 통과했다.
6. **패키징:** 6개 배포의 wheel/sdist 12개를 빌드했고 Twine 검사가 모두 통과했다. Vault 루트 요구사항만으로 로컬 인덱스에서 6개 wheel의 SHA256을 검증해 설치했다. 워크플로 YAML 4개를 파싱했다.
7. **독립 리뷰:** 리뷰 에이전트가 계약과 세 패키지·Vault 연동 코드를 검토했다. 발견한 삭제 범위·모델 출처·식별자·입력 검증·저장 안전성·코어 순수성 문제를 수정하고 회귀 검사했다. 최종 리뷰에서 남은 중요 문제는 발견되지 않았다.

## 재현 명령

```bash
uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/graph-search/tests packages/graph-document/tests packages/text-embeddings/tests packages/vector-search/tests packages/vector-index/tests
uv run --python 3.12 ruff check src tests packages
uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/text-embeddings/tests packages/vector-search/src packages/vector-search/tests packages/vector-index/src packages/vector-index/tests
uv lock --check
uv run --python 3.12 python tests/verify_graph_module_wheels.py
uv build --all-packages --out-dir /tmp/vault-graph-vector-modules-dist
uv run --python 3.12 --with twine python -m twine check /tmp/vault-graph-vector-modules-dist/*
```

## 보장 범위와 제한

- 범용 저장 변경은 Chroma와 보조 SQLite 갱신을 묶은 원자적 트랜잭션이 아니다. Vault에서는 비활성 세대에 쓰고 성공한 세대만 발행한다.
- 계획 재검증은 원자적 비교·갱신이나 작성자 잠금이 아니다. 병렬 작성자는 호출자가 조정한다.
- 임베딩 실행 검증은 구성한 결정적 백엔드로 수행했다. 실제 사전학습 모델의 다운로드·추론 품질·새 성능 SLA는 이번 검증에 포함하지 않았다. 모델 경로와 선언한 버전의 일치는 호출자가 보장한다.
- 기존 Vault 저장 식별자를 변경하지 않는다. 기존 ID 생성 규칙의 충돌 입력은 덮어쓰기 전에 거부한다.
- PyPI/TestPyPI 업로드와 원격 GitHub Actions 실행은 수행하지 않았다. 결과는 로컬 구현·검증 완료를 뜻한다.
