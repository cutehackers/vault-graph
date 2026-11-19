# 기억 드리밍: 수집 뒤 세션 교환을 근거 인용이 붙은 기억 제안으로 바꾸기

- 날짜: 2026-11-19
- 상태: 승인됨 (사용자, 2026-11-19, 소유자 결정 OD1~OD4를 권고안대로 승인)
- 바탕 글: Anthropic "The Components of Agent Memory" (2026-11-06, https://www.anthropic.com/research/components-of-agent-memory)
- 논의: 아키텍트 에이전트와 에이전트 기억 연구자 에이전트가 세 차례 논의해 합의했다. 요약은 §9.

## 1. 목표와 지금의 문제

드리밍은 세션이 수집된 뒤 뒤에서 돌면서, 기억으로 쓰이지 않은 세션 교환을 읽고 "기억할 만한 것"을 Vault 검토 대기열에 추론 제안으로 올린다. 사람이 `review resolve`로 승인한 것만 기억이 된다. 사용자가 "기억 정리해"라고 말하지 않아도 세션 내용이 기억 후보로 바뀌는 것이 목표다.

측정된 문제:

- 대기 중인 세션 교환이 546개이고 나이 중앙값이 6.62일이다. 기준은 7일이다 (`docs/TODO.md` 남은7).
- 수동 정리 두 번에서 후보 40개 중 3개만 발행됐고 추론 제안은 0개였다 (`docs/design/reports/2026-11-curation-trial.md`).
- 이미 발행된 페이지가 나중 세션과 어긋나는지 확인하는 단계가 없다. 폐기 신호는 `code_gone`과 `unused`뿐이다.
- 추론 제안 승인율은 한 번도 측정되지 않았다.

글에서 가져온 것:

- 세션 원문을 사실 기준으로 삼아 기억을 고친다 (D3).
- 여러 세션에 흩어진 내용을 세션 밖에서 모아 본다 (D2).
- 늘 주입되는 최상위 층은 사람이 승인한 변경으로만 바뀐다 (C6).
- 무엇을 위한 기억인지 알려 주고, 굳은 규칙은 쓰기 경계에만 둔다 (D2 프롬프트).

## 2. 범위

### D1. 인용 확인

- 인용문이 실제로 그 세션 교환의 사람 턴 안에 있는지 확인하는 순수 함수다.
- 유니코드 NFKC로 맞추고 공백을 한 칸으로 줄인 뒤 부분 문자열인지 본다. 한국어 인용이 통과해야 한다.
- 인용문은 정규화한 뒤 8자 이상이어야 한다. 한두 글자 인용은 어디에나 있어서 확인이 되지 않는다.
- 위치: `src/vault_graph/operation/memory/evidence_quote.py` (M18, 파일을 읽지 않는다).
- 한계: 인용문이 있다는 것만 증명한다. 제안 내용이 인용문에서 나오는지는 사람이 검토한다.

### D2. 수집 뒤 제안 전용 실행

- 입력: `session_exchange` 후보. 후보마다 교환 원문, 사람 턴 글, 비교 페이지를 붙인다. L1 노트는 뺀다. L1 노트를 근거로 쓰려면 `import-source`가 `raw/`에 써야 하는데, 사람 없이 그 쓰기를 하지 않는다.
- 판단: `claude -p --model <model> --json-schema <schema> --no-session-persistence --tools "" --strict-mcp-config`. 도구와 MCP 서버가 없다. 자식 환경에 `VAULT_GRAPH_FACTS_CHILD=1`을 넣어 자식 세션의 훅이 수집도 회상도 하지 않게 한다.
- 자식의 답: 후보마다 `remember`, `update_memory`, `supersede_claim`, `none` 중 하나와 인용문. 위치는 받지 않는다. 위치는 vg가 만든 후보의 것만 쓴다.
- 프롬프트: 무엇을 위한 기억인지 한 문단으로 알린다("이 프로젝트의 다음 세션에서 사용자가 같은 말을 다시 하지 않게 한다"). 새 페이지보다 기존 페이지 수정과 주장 교체를 먼저 고르게 한다. 글은 대상 페이지의 언어로, 새 페이지는 인용문의 언어로 쓴다. 신호 단어 목록은 없다.
- 쓰기: 작업자가 D1로 인용을 확인한 뒤 `MemoryWriteService`를 `basis="inferred"`로만 부른다. 길은 기존 둘째 길 `review propose`다. 새 쓰기 경로는 없다.
- 근거 줄: 작업자가 확인된 위치와 인용문으로 직접 만든다. 자식이 쓴 글을 근거 줄에 넣지 않는다.
- 건너뜀: `none` 답은 `memory/reviewed.jsonl`에 적지 않는다. 적으면 수동 정리에서 그 후보가 사라진다. 대신 Graph Home `dream/judged.jsonl`에 적고, 이 파일은 드리밍 작업자만 읽는다. 기록마다 프롬프트 버전과 모델을 적고, 버전이나 모델이 다른 기록은 무시한다.
- 제안된 후보: `memory/reviewed.jsonl`에 결과 `dream_proposed`로 적어 수동 제안(`proposed`)과 구분한다.
- 지키는 한도:
  - 한 번 실행에 제안 `min(실행당 한도, 대기 한도 − 지금 대기 수)`개까지.
  - 저장 Vault의 대기 제안이 대기 한도 이상이면 실행하지 않는다.
  - 프로젝트마다 24시간에 한 번.
  - 한 번에 하나만 실행한다 (`logs/dream-worker.lock` flock).
- 최상위 층 보호: `pin`을 바꾸지 않는다. `kind="project"`(brief)를 만들지 않는다. 고정된 페이지와 프로젝트 brief는 수정 대상에서 뺀다.
- 실행 조건: 드리밍이 켜져 있고, (대기 나이 중앙값이 7일을 넘었거나, 아직 판단하지 않은 교환이 20개 이상)일 때.

### D3. `verify` 후보

- 지금 쓰이는 기억 페이지마다, 그 페이지보다 나중에 시작된 같은 주제의 세션 교환을 근거 모드 검색으로 찾는다.
- 자식은 `supersede_claim`(주장 한 줄 교체)이나 `retire_memory`(폐기)를 제안하거나 `none`을 답한다. 언제나 `inferred`다.
- 제안마다 두 가지를 확인한다. 교체할 주장 줄이 페이지에 실제로 있는지, 새 인용문이 그 교환의 사람 턴에 있는지.
- "나중"인지는 교환 메타데이터의 시각과 페이지의 날짜로 정한다. 자식이 말한 날짜는 쓰지 않는다.
- 대기 중인 제안과 `.facts.md`는 읽지 않는다.

### D4. 수동 흐름의 인용 확인

- MCP 쓰기 도구에 선택 인자 `quote`를 더한다.
- `basis="stated"`이고 근거가 세션 교환 위치를 가리키면 `quote`가 있어야 하고 D1을 통과해야 한다.

## 3. 사용자가 보는 것

- `vg dream on|off|status`
- `vg dream run [--cwd PATH] [--dry-run]`: 손으로 한 번 실행한다. 켜짐 여부, 24시간 간격, 실행 조건은 보지 않고 대기 한도는 지킨다. `--dry-run`은 판단까지만 하고 Vault와 기록 파일에 아무것도 쓰지 않는다.
- `vg dream worker`: 훅이 띄우는 내부 명령.
- CLI 출력은 `vg facts`처럼 영어다.
- MCP 도구와 프롬프트는 D2에서 바뀌지 않는다. 세션 시작에는 기존 줄 "승인을 기다리는 추론 제안: <Vault> N개"가 결과를 알린다. 회상은 계속 LLM을 부르지 않는다.
- `status`는 설정, 마지막 실행, 보낸 제안 수, 승인·거부·대기 수를 보이고, 대기 한도 때문에 멈췄으면 "stopped: pending cap reached"를 보인다.

## 4. Graph Home에 두는 것

모두 지워도 기억은 바뀌지 않는다.

| 파일 | 내용 |
|---|---|
| `configs/dream.json` | `version`, `enabled`, `model`, `pending_cap`, `proposals_per_run`, `interval_hours`, `bundle_limit`, `due_exchanges` |
| `dream/judged.jsonl` | 판단은 했지만 제안하지 않은 후보. 비용을 두 번 쓰지 않기 위한 기록이다 |
| `logs/dream-runs.jsonl` | 실행마다 한 줄. 보낸 제안의 `review_path`가 들어 있어 승인율을 드리밍 제안만으로 센다 |
| `logs/dream-worker.lock`, `logs/dream-worker.log` | 작업자 잠금과 출력 |

## 5. 하지 않는 것

| 항목 | 이유 |
|---|---|
| 사람 없이 발행 | 추론한 사실은 승인될 때까지 검토 대기열에 둔다 (`docs/SPEC.md` §0 규칙2) |
| 고정(pin) 제안 | 잘못된 고정은 모든 세션에 들어간다. 자동 선택을 뒷받침하는 측정이 없다 |
| 드리밍이 만드는 위키, 통째 다시 쓰기 | Vault에 기계가 만든 요약을 쓰지 않는다. 글에서도 위키가 원문보다 1.77배 커진 사례가 있다 |
| 링크·고아 페이지 고치기 | Vault lint가 이미 한다 |
| 별칭 만들기 | 측정된 문제가 없다 |
| 로컬 모델로 드리밍 | 글에서 정리 품질이 모델 세대에 크게 좌우됐다. 재기 전에는 쓰지 않는다 |
| 후보 정렬 규칙 변경 | `9fbe9f7` 뒤 신호 단어의 정확도를 다시 재지 않았다 |
| 뒤 실행에서 L1 노트·병합·brief 후보 | 수동 흐름에 남긴다 |

## 6. 소유자 결정 (2026-11-19 승인)

- OD1: 수집 뒤 뒤에서 `inferred` 제안을 검토 대기열에 보내는 실행을 허용한다. "훅은 정리하지 않는다"와 "수집 뒤 LLM 사용은 세션 사실 하나"를 고친다.
- OD2: 기본은 꺼짐이다. `vg dream on`으로 켠다. 승인율이 해결된 제안 30개에서 0.7 이상이 되면 기본값을 다시 정한다.
- OD3: 대기 한도 10(저장 Vault마다), 실행당 제안 10, 프로젝트마다 24시간에 한 번, 묶음 40, 실행 조건의 미판단 교환 수 20.
- OD4: 모델은 `claude-sonnet-5-5`다.

## 7. 수용 기준

테스트:

- `tests/test_evidence_quote.py`: 한국어, 공백, 사람 턴 밖 인용, 짧은 인용.
- `tests/test_dream_settings.py`: 없는 파일은 꺼짐, 깨진 파일은 꺼짐과 이유.
- `tests/test_dream_judge.py`: 명령 줄, 답 확인.
- `tests/test_dream_worker.py`: 인용이 틀리면 아무것도 보내지 않는다. `none`은 `reviewed.jsonl`을 건드리지 않는다. 대기 한도와 24시간 간격이 실행을 막는다. `basis`는 언제나 `inferred`다. 고정 페이지와 brief는 거부한다. 판단 기록의 버전이 다르면 다시 판단한다.
- `tests/test_hook_dream.py`: 꺼져 있으면 작업자를 띄우지 않는다. 자식 환경에서는 훅이 조용하다.
- `tests/test_memory_candidates_verify.py`: D3 후보 규칙과, 심어 둔 오류와 음성 대조군을 쓰는 시험.

확인 명령 (`.github/workflows/ci.yml`):

- `uv run --python 3.12 ruff check src tests packages`
- `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests`

측정:

| 값 | 지금 | 통과 조건 |
|---|---|---|
| 드리밍 제안 승인율 (`logs/dream-runs.jsonl`의 `review_path`만) | 값 없음 | 처음 해결된 30개에서 0.7 이상. 이것이 첫째 조건이다 |
| 실행당 제안 수, D1이 거른 수 | 추론 0 | 보고 |
| 대기 교환에만 답이 있는 질문 20개 이상의 context hit | 값 없음 | 승인 전후를 보고 |
| 기존 질문의 context hit | 0.92 | 떨어지지 않음 |
| 실행당 비용 | 수동 $0.40~$0.57 | 보고 |
| 대기 나이 중앙값 | 6.62일 | 보고만 한다. 통과 조건으로 쓰지 않는다. 건너뛰기만 하는 실행도 이 값을 낮추기 때문이다 |
| D3 심은 오류 시험 | 없음 | 정밀도와 재현율 보고 |

승인율과 승인 전후 측정은 사람이 실제 제안을 해결해야 값이 생긴다.

## 8. 구현 순서

1. 이 문서, `docs/DECISIONS.md`, `docs/SPEC.md`, `AGENTS.md`.
2. D1과 테스트.
3. `dream_settings.py`와 `vg dream on|off|status`.
4. 판단 어댑터: 스키마, 프롬프트, 답 확인.
5. 작업자와 `vg dream run --dry-run`.
6. 제안 보내기, 한도, `dream/judged.jsonl`, 실행 기록.
7. 수집 훅에서 작업자 띄우기.
8. dry-run 측정과 보고서.
9. D3와 심은 오류 시험.
10. D4.

## 9. 논의 요약

- 1차: 아키텍트는 `curate_memory` 전체를 사람 없이 돌리자고 했고, 연구자는 Graph Home에 미리 판단한 후보 파일을 두자고 했다.
- 2차: 둘이 서로의 안으로 옮겼다. 아키텍트는 사람 없는 프로세스가 "사용자가 말했다"를 판정하고 발행하는 것이 과하다고 봤다. 연구자는 후보 파일이 기계 판단의 둘째 저장소가 되고, 여전히 "기억 정리해"를 기다린다고 봤다.
- 3차 합의: 출력은 검토 대기열 하나다. 자식에게는 도구를 주지 않고, 작업자가 인용을 확인한 뒤 `inferred`로만 보낸다.
- 연구자가 서명 조건으로 건 변경 8개:
  - C1: 인용은 인용된 줄 범위의 사람 턴 안에 있어야 한다.
  - C2: 판단 기록에 있는 후보를 먼저 빼고 나서 묶음 크기로 자른다. 그러지 않으면 같은 40개만 다시 본다.
  - C3: 실행 조건에 "미판단 교환 N개 이상"을 더한다. 지금 중앙값 6.62일로는 7일 조건이 걸리지 않는다.
  - C4: 실행당 한도는 `min(10, 대기 한도 − 대기 수)`다.
  - C5: 근거 줄은 작업자가 만든다. 드리밍 제안은 `dream_proposed`로 적는다.
  - C6: `pin`, brief, 고정 페이지를 건드리지 않는다.
  - C7: 자식 명령에 `--no-session-persistence`를 넣는다.
  - C8: 승인율은 드리밍 실행 기록의 제안만으로 센다. 대기 교환에만 답이 있는 질문으로 전후를 잰다.
- 남은 점: 사람이 제안을 해결하지 않으면 대기 한도가 드리밍을 멈추고 승인율 값도 생기지 않는다. 첫 버전은 이것을 받아들이고 `status`에 멈춘 이유를 보인다.

## 10. 구현하면서 정한 것

설계에 없던 세부를 코드에서 이렇게 정했다.

- 대기열 파일을 두지 않는다. 훅은 `vg dream worker --cwd <cwd>`를 바로 띄우고, 잠금이 잡혀 있으면 띄우지 않는다. 실행 조건은 상태로 정해지므로 다음 수집이 다시 시도한다.
- 자식은 위치를 답하지 않는다. 위치는 vg가 만든 후보의 것만 쓴다. 인용 확인은 그 후보의 사람 턴 글에 대해 한다 (C1).
- `update_memory`는 덧붙이기만 한다. 자식은 덧붙일 글(`addition`)을 답하고, 작업자가 지금 본문 뒤에 붙인다. 페이지가 `remember`가 쓰는 모양(제목, 본문, `## Evidence` 하나)이 아니면 거부한다. 기존 근거 줄은 남긴다. 승인되면 페이지의 `Status` 줄은 `inferred`가 된다. 수동 `update_memory(basis="inferred")`와 같은 동작이다.
- 대상 페이지는 그 항목에 보여 준 페이지만 된다. 항목마다 비교 페이지 3개까지, 페이지 글은 3,000자까지, 교환 글은 6,000자까지 보여 준다.
- 한 번에 교환 8개를 판단한다. 실행 한도를 채우면 남은 묶음은 판단하지 않는다.
- `verify`는 실행마다 한 묶음(8개)이고, 세션 교환 판단 뒤 한도가 남을 때만 한다. 세션 교환 대기열이 실행 조건에 못 미쳐도 `verify`는 한다. 페이지마다 나중 교환은 최신 2개까지다. 근거 줄에 그 교환이 시작된 날을 색인에서 가져와 붙인다.
- `verify` 항목의 판단은 `supersede_claim`, `update_memory`, `retire_memory`, `none`이다. `update_memory`는 주장 표가 없는 페이지(`remember`가 쓴 페이지)를 고치는 길이다. 덧붙이는 글 첫머리에 무엇이 언제부터 맞지 않는지 적게 한다.
- 같은 교환으로 같은 실행에서 두 번 제안하지 않는다. `verify` 제안을 보내면 그 교환의 `session:` 키도 함께 기록하고, `session:` 키가 기록된 교환은 `verify` 후보로 올리지 않는다.
- 한 실행에서 한 페이지에는 변경 제안을 하나만 보낸다. 판단이 읽은 뒤 페이지가 바뀌었으면 보내지 않고 다음 실행에서 다시 판단한다.
- `verify`는 정리 꾸러미 종류가 아니다. `CandidateKind`와 MCP 도구 스키마에 넣지 않고 `AnyCandidateKind`로 따로 둔다.
- 판단 결과는 `none`, `no_answer`(판단이 그 항목을 빼먹음. 두 번 기록된 뒤에야 판단한 것으로 본다), `invalid_answer`, `quote_rejected`, `target_refused`, `vault_rejected`(이상 `dream/judged.jsonl`에 기록), `proposed`, 그리고 기록하지 않는 `deferred`(한도, 바뀐 페이지, 같은 페이지 둘째 변경, 그사이 사람이 처리함)와 `vault_error`(Vault 명령 오류)다.
- 기록은 그때그때 쓴다. 제안은 보낸 즉시 `memory/reviewed.jsonl`과 `logs/dream-runs.jsonl`의 `proposal` 줄에 적고, 판단 기록은 묶음마다 적는다. 실행이 중간에 죽어도 보낸 제안을 다시 보내지 않고 승인율에서 빠지지 않는다.
- `logs/dream-runs.jsonl`에는 `proposal` 줄과 `run` 줄이 있다. 판단한 것이 없어 건너뛴 실행(`nothing_to_judge`, `not_due`)과 대기 한도에 막힌 실행(`pending_cap`, 연달아 한 번만)도 `run` 줄로 남긴다. 그래서 드리밍 제안이 하나도 없을 때도 `status`가 멈춘 이유를 보인다.
- 실패한 실행(판단 명령을 쓸 수 없음)은 1시간 뒤 다시 시도한다.
- 판단 명령은 `--output-format json`으로 실행해 답(`structured_output`)과 비용(`total_cost_usd`)을 함께 받는다.
- D4: `quote`는 `remember`, `update_memory`, `supersede_claim`에 있다. `retire_memory`와 `restore_memory`는 근거 인자가 없어 넣지 않았다.
  - 근거에 세션 파일(`raw/sessions/...md`)이 있고 `basis`가 `stated`면 `quote`가 있어야 한다. 줄 범위를 빼도 확인을 건너뛰지 못한다. 줄 범위가 없으면 `rejected`다.
  - 인용한 범위는 교환마다 나눠 읽는다. 하위 에이전트 교환에 걸친 범위를 인용해도 하위 에이전트에게 준 프롬프트는 사용자 글로 세지 않는다.
  - 세션 파일은 저장 Vault에서 먼저 찾고, 없으면 그 프로젝트에 연결된 다른 Vault에서 찾는다. 어디에서도 읽을 수 없으면 `rejected`다.
- 프롬프트 버전은 `dream-2`다. 프롬프트 글이 바뀌면 테스트가 실패해 버전을 올릴지 정하게 한다.
- C8: 드리밍 전에 대기 교환으로 질문 26개를 써 두었다(`tests/benchmarks/measure_dream_backlog.py`, 질문 파일은 저장소 밖).
- 측정 결과는 `docs/design/reports/2026-11-dreaming-dry-run.md`에 있다.
