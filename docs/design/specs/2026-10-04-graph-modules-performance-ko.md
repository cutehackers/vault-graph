# 독립 그래프 모듈의 성능 목표와 측정 계약

- 사용자 요청: 유사 제품의 공개 수치를 조사하여 성능 목표를 정한다.
- 범위: 일반 그래프 탐색, 명시한 관계의 문서 그래프 색인·조회, 기존 Vault 투영 어댑터.
- LLM·임베딩·원문 파싱·원격 전송 시간은 이번 모듈 지연 시간에 포함하지 않는다.

## 1. 참고한 공개 결과

| 참고 | 공개한 조건과 수치 | 이 설계에 적용하는 범위 |
| --- | --- | --- |
| 참고1 | Memgraph 2.4 / Neo4j 5.1 Community 비교에서 1-hop Q5는 1.09 / 27.96ms, 2-hop Q7은 6.10 / 88ms. | 제한된 연결 탐색은 밀리초 단위로 목표를 정한다. 이 값은 평균 성격의 DB 질의 수치이며 우리 p95 측정값이 아니다. |
| 참고2 | Benchgraph 후속 설명은 Pokec medium 100,000 nodes/1.7M edges, 서로 다른 warm-up과 동시 client 수를 구분한다. 복잡한 LDBC 질의 중 p99가 1초를 넘는 사례도 있다. | 그래프 모양·후보 경로 수·동시성·캐시 상태를 기록한다. 단순 연결 탐색과 모든 경로 열거의 목표를 분리한다. |
| 참고3 | Neo4j Docker 기본 구성은 heap 최대값과 page cache를 각각 512M으로 설정한다. 공식 문서는 학습용 기본값이며 운영 환경에 맞게 조정해야 한다고 설명한다. | 수백 MiB 단위의 자원 예산을 참고한다. JVM heap·page cache와 우리 프로세스 RSS를 같은 값으로 비교하지 않는다. |

출처: [Memgraph의 2022년 비교 보고](https://memgraph.com/blog/how-to-choose-a-graph-database-for-your-real-time-application),
[2023년 Benchgraph 방법과 한계](https://memgraph.com/blog/benchgraph-backstory-the-untapped-potential).
[Neo4j Docker 메모리 구성](https://neo4j.com/docs/operations-manual/current/docker/configuration/)과
[heap·native memory 구분](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)도 확인했다.
벤더가 작성한 과거 버전의 결과다. 최신 제품의 성능 보장이나 독립 평가로 해석하지 않는다.
후속 글도 이전 결과가 오래되었다고 밝히므로, 역사적 참고 수치로만 사용한다.
DB 서버의 K-hop 확장과 Python에서의 단순 경로 전량 열거·근거 조립은 같은 작업이 아니다.
LLM 없이 문서 관계만 추출·저장하는 동등한 공식 벤치마크는 찾지 못했다.

## 2. 이번 구현의 목표

다음 수치는 공개 결과의 시간 규모와 모듈별 책임을 바탕으로 정한 **자체 엔지니어링 목표**다.
비교 제품의 수치를 그대로 가져오거나, 측정 후 통과할 수 있게 목표를 완화하지 않는다.

| 코드 | 고정한 대표 입력과 작업 | 지연 목표 | 메모리 목표 |
| --- | --- | --- | --- |
| 성능1 | 이미 생성한 501-node/500-edge star snapshot, BFS depth 1–2. | warm p95 ≤20ms | 별도 측정·기록. |
| 성능2 | 같은 star 입력, 기존 점수·중복·top-50를 보존하는 Vault projection. | warm p95 ≤100ms | 별도 측정·기록. |
| 성능3 | 3 nodes, seed→middle 250개 + middle→target 250개 평행 간선, depth=2, 62,750 후보 경로. core 전량 열거와 Vault projection을 각각 측정. | warm p95 각각 ≤2,000ms | adapter Python allocation peak ≤96MiB. |
| 성능4 | 1,000 documents ×4,096-character ASCII text, 문서마다 공유 tag 2개. 일반 규칙 추출과 durable initial commit. | fresh DB 5회 모두 ≤10s | Python allocation peak ≤128MiB. |
| 성능5 | 같은 collection에서 문서 1개 변경과 durable commit. | 5회 모두 ≤1,000ms | 별도 측정·기록. |
| 성능6 | 같은 collection 중 문서 1개 선택 SQL read, search bridge와 같은 snapshot의 evidence lookup. | warm p95 ≤100ms | 범위 밖 문서·근거가 결과에 유입되지 않아야 한다. |
| 성능7 | 같은 collection 전체 immutable read. | warm p95 ≤500ms | 별도 측정·기록. |
| 성능8 | 실제 Vault 문서 1,000개 약4KiB, 새 저장소에서 revision 검증과 호환 SQL 조회 상태를 생성하는 읽기 전용 open. | 20회 p95 ≤2,000ms | Python allocation peak ≤128MiB. |
| 성능9 | 같은 저장소를 연 상태에서 실제 GraphRetrievalService의 related 조회와 MetadataStore 근거 확인. | 20회 warm p95 ≤200ms | 반복 요청의 저장소 수명주기와 메모리 사용을 별도 확인. |

성능8–9는 순서7의 전환 경로를 대상으로 측정 전에 추가했다. 성능8은 성능7의 전체 snapshot
조회에 대응표 검증과 SQL 상태 구성을 포함하므로 2초로 정한다. 성능9는 성능2의 탐색·순위
100ms에 최신성·근거 확인 비용을 추가한 200ms 목표다. 이 값도 자체 목표이며 제품 벤치마크의
보장 수치를 의미하지 않는다. 최초 CLI 색인과 저장소 이전 시간은 조회 목표에 포함하지 않는다.

표본 5개의 쓰기 최대값을 p95/p99로 과장하지 않는다. 조회·탐색은 warm-up 후 최소20회 측정하여
표본 수와 p50/p95를 보고한다. p99 및 다중 사용자 지연 보장은 이번 결과로 주장하지 않는다.
자원 상한에 걸리면 완료된 정상 결과로 표시하지 않는다. 입력 범위를 임의로 줄여 기존 유효 요청을 거부하지 않는다.

## 3. 검증과 운영 해석

기준 환경은 Python 3.12, 로컬 SSD, 단일 프로세스·단일 요청이다. 실제 OS/CPU 정보를 측정 결과에 기록한다.
tracemalloc은 별도 실행에서 Python allocation peak만 측정하며, native allocation과 process RSS의 상한을 뜻하지 않는다.
지연 시간 측정에서는 tracemalloc을 끈다. 초기 연결·snapshot 생성 시간을 제외한 항목은 그 경계를 명시한다.

단위 테스트에는 CPU 속도에 따른 임의 timeout을 넣지 않는다. 성능 측정은 별도 명령으로 반복하며
결과와 목표 충족 여부를 구현 계획에 기록한다. CI 기능·정합성 통과와 로컬 성능 목표 통과는 구분한다.
성능8의 저장소 open 외의 cold start, 여러 writer, 1,000문서 초과, 대규모 본문·LLM·HTTP 전체 응답 시간은 별도 부하 측정이 필요하다.

## 4. 실행 결과

명령: `uv run --python 3.12 python tests/benchmarks/measure_graph_modules.py`.
[원시 결과](../reports/2026-10-04-graph-modules-performance.json)는 macOS 27.0.1 arm64,
12 logical CPUs, Python 3.12.11, rustworkx 0.17.1 환경에서 3 warm-up 후 측정했다.

| 코드 | 실제 결과 | 판단 |
| --- | --- | --- |
| 성능1 | p95 0.291ms | 20ms 이내. |
| 성능2 | p95 9.202ms | 100ms 이내. |
| 성능3 | core p95 54.394ms, adapter p95 323.975ms, adapter Python allocation peak 48.60MiB. | 두 지연·메모리 목표 이내. |
| 성능4 | 5회 최대 651.246ms, Python allocation peak 20.96MiB. | 10s·128MiB 이내. |
| 성능5 | 5회 최대 112.341ms. | 1,000ms 이내. |
| 성능6 | p95 0.341ms. | 100ms 이내. |
| 성능7 | p95 200.498ms. | 500ms 이내. |

출력의 원시 표본을 고정한 목표와 대조했다. 기존 투영 결과의 완전 일치, 예상한 문서 그래프의
1,002 nodes/2,000 edges/5,000 evidence, DB에 본문 marker가 저장되지 않음도 실행 중 검사했다.
root의 별도 전체 재실행에서도 같은 목표를 충족했다. 이는 명시한 로컬 대표 부하의 결과이며
동시 사용자·원격 배포·모든 입력의 SLA를 증명하지 않는다.

순서7의 실제 Vault 운영 경로는 다음 명령으로 검증했다.
`uv run --python 3.12 python -m tests.benchmarks.measure_document_graph_backend`.
1,000문서·4,096바이트/문서, 1,002 entities·2,999 relationships를 실제 CLI로 색인하고 전환했다.
동일한 목표와 입력을 유지한 [수정 전 측정](../reports/2026-10-04-document-graph-backend-performance-before-fixes.json)은
open p95 3,260.981ms, related p95 2,956.844ms, Python allocation peak 약2GiB로 실패했다.
manifest 파일 크기에 맞춘 읽기, 같은 검증 호출의 snapshot·레코드 재사용, 근거 일괄 조회,
마지막 한 scope의 graph manifest 재사용 후 [최종 측정](../reports/2026-10-04-document-graph-backend-performance.json)을 수행했다.

| 코드 | 최종 실제 결과 | 판단 |
| --- | --- | --- |
| 성능8 | 새 저장소 open 20회 p95 1,321.372ms, 전체 Python allocation peak 73.451MiB. | 2,000ms·128MiB 이내. |
| 성능9 | 실제 related 조회 20회 warm p95 128.210ms. | 200ms 이내. |

3회 warm-up, 별도 tracemalloc 실행, OS page cache를 유지한 새 저장소 객체 생성이라는 경계는 그대로다.
Vault 및 Data Home의 전체 파일 해시는 조회 전후 동일했다. 스크립트는 목표나 읽기 전용 검증이
실패하면 결과 JSON을 보존하고 실패 종료한다. 원격 환경이나 패키지 인덱스 설치를 검증한 결과는 아니다.

## 5. 실제 프로세스 메모리와 저장 크기 검증

GS의 준비·BFS·경로 열거·경로 복원·어댑터와 DG의 추출·저장·읽기는 최대 RSS도 별도로 측정한다.
각 단계마다 새 프로세스를 실행하여 import와 입력 준비를 포함한 프로세스 전체 최대값을 기록한다.
`resource.getrusage(RUSAGE_SELF).ru_maxrss`의 macOS 바이트·Linux KiB 단위를 바이트로 통일한다.
이 측정은 OS에서 메모리 제한을 강제하거나 임의 입력의 최대값을 보장하는 기능이 아니다.

측정 전에 다음 자체 목표를 고정한다. 앞의 성능1–9와 입력 및 목표는 유지한다.

| 코드 | 고정한 입력과 범위 | 목표 |
| --- | --- | --- |
| 자원1 | 501-node/500-edge star 또는 3-node/500-edge parallel, 단계별 새 프로세스의 전체 최대 RSS. | 각 단계 ≤512MiB. |
| 자원2 | 일반 1,000-document·4KiB·공유 tag 2개 fixture의 추출·durable commit·읽기·bridge, 단계별 새 프로세스의 전체 최대 RSS. | 각 단계 ≤512MiB. |
| 자원3 | 같은 문서 fixture의 SQLite DB와 남아 있는 WAL·SHM 파일의 합계. | ≤64MiB. |

512MiB는 Python allocation 목표 최대128MiB에 런타임·native memory·입력 준비 예산384MiB를 더한
자체 운영 기준이다. Neo4j의 512M 기본 설정과 동일한 처리량이나 메모리 효율을 주장하지 않는다.
64MiB는 원문 약4MiB 규모의 입력에 대해 근거·revision·인덱스 저장 비용을 확인하는 자체 기준이다.
이 모듈 전용 프로세스 기준을 임베딩·벡터 저장소를 불러오는 Vault Graph 전체 프로세스에 적용하지 않는다.
명령 `uv run --python 3.12 python tests/benchmarks/measure_graph_module_rss.py`를 root가 재실행했다.
[원시 결과](../reports/2026-10-04-graph-module-rss.json)의 11개 단계 모두 목표를 충족했다.
새 배포명 `nolemy-graph-search`·`nolemy-graph-document`로 재실행한 전체 최대 RSS는
90,521,600 bytes(86.328MiB), DB+WAL+SHM 최대 합계는
6,447,104 bytes(6.148MiB)였다. 별도 reviewer도 측정 방식과 고정 입력을 검토했다.
문서 읽기·bridge 단계의 최대 RSS와 elapsed_ms에는 해당 프로세스의 fixture DB 생성도 포함된다.
이 시간은 성능6–7의 순수 조회 p95를 대신하지 않는다. DB 크기는 저장소를 닫은 뒤의 크기다.
