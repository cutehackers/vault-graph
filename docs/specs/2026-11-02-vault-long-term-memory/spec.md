# Spec: vault-graph를 여러 Vault 위의 장기 기억 도구로 완성

## 1. Problem

- 작업 id: `20261102-vault-graph-vault-intent-7487`. 경로: design-first.
- 대상 저장소 두 개:
  - vault-graph: 이 worktree, 브랜치 `feat/jh/local-graph`. 기준은 0a9057b와 커밋하지 않은 `docs/SPEC.md` §0, `docs/DECISIONS.md` 2026-11-02 항목이다.
  - vault-builder: `$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`, 기준 f562d77.
- 경로 표기: 앞에 `vault-graph:` 또는 `vault-builder:`를 붙인다. 붙이지 않은 경로는 vault-graph 경로다.

`docs/SPEC.md` §0(2026-11-02)은 vault-graph를 "여러 Vault 위의 장기 기억 도구"로 다시 정했다. 지금 코드와 Vault 도구는 이 정의의 절반만 한다. 아래 발견은 파일을 직접 읽어 확인했다. 확인 방법은 각 줄의 근거 열에 적었다.

| 코드 | 지금 상태 | 근거 |
|---|---|---|
| 발견1 | 범위를 주지 않은 검색은 활성 Vault 하나만 찾는다. MCP `search_vault`는 `cwd`를 받지 않는다. 프로젝트에 연결된 Vault 전부를 찾는 함수 `resolve_project_vaults`는 세션 시작 회상만 쓴다. | `src/vault_graph/operation/scope/vault_catalog.py:142-144`, `src/vault_graph/interface/mcp/mcp_tools.py:675-692`, `src/vault_graph/interface/composition/query_scope_resolution.py:38-70` 읽음 |
| 발견2 | 검색 결과에는 `vault_id`만 있다. Vault 이름과 종류(`role`)가 없다. `vault_id`는 `vault-map.json`의 이름과 다를 수 있다(이미 다른 id로 등록된 경로는 그 id를 쓴다). | `src/vault_graph/interface/mcp/mcp_tool_serialization.py:576-595`, `src/vault_graph/interface/cli/main.py:432-434` 읽음 |
| 발견3 | 기본 저장 Vault가 없다. `remember`는 Vault가 여럿이면 일반 `error`로 "Pass vault."를 돌려준다. `vault_required` 같은 구분된 응답이 없다. 명시한 `vault`를 프로젝트에 연결된 Vault로 좁히지 않고 map 전체에서 찾는다. | `src/vault_graph/operation/integration/remember_service.py:133-151` 읽음. `vault-map.json` 쓰기 코드 `vault-builder:tools/vault_migration/installing.py:352-390`, `linking.py:60-72`에 기본 저장 필드 없음 |
| 발견4 | `remember`는 새 페이지 추가만 한다. 같은 경로가 있으면 거부한다. 수정·폐기 경로가 없다. | `remember_service.py:107-122` 읽음 |
| 발견5 | Vault에는 대체 없는 폐기 방법이 없다. 페이지 status는 `seed\|active\|stable\|contested\|deprecated`이고, `deprecated`는 `superseded_by`가 필수다. | `vault-builder:tools/wiki/lib/schema.py:49`, `vault-builder:tools/wiki/lib/lint.py:433-441` 읽음 |
| 발견6 | `patch-page` draft는 `edits`가 비어 있으면 거부한다. 그래서 frontmatter만 바꾸는 폐기를 patch로 표현할 수 없다. | `vault-builder:tools/wiki/lib/draft_patch.py:42-44` 읽음 |
| 발견7 | publish-draft는 텍스트만 출력한다. vault-graph는 `Applied draft:` 줄과 `Publish aborted:` 문구를 문자열로 찾아 결과를 판단한다. 발행 로직이 `cli.py` 안의 비공개 함수라 다른 Vault 명령이 다시 쓸 수 없다. | `vault-builder:tools/wiki/cli.py:103-105, 705-745`, `src/vault_graph/interface/composition/adapters/vault_publish_cli.py:21-63` 읽음 |
| 발견8 | 검토 대기열 유형은 `contradiction\|merge\|contested-claim\|human-lock`뿐이다. 검토 항목에 draft를 붙일 수 없고, `review resolve`는 상태만 바꾸고 로그를 남긴다. 승인해도 wiki에 반영되지 않는다. | `vault-builder:tools/wiki/lib/review.py:15-17, 241-268` 읽음 |
| 발견9 | Vault frontmatter에 `pin`, `memory_kind`, 스키마 버전 필드가 없다. 그래서 회상 구획A(고정 기억)는 늘 비어 있다. | `vault-builder:tools/wiki/lib/schema.py:8-47`, `src/vault_graph/context/pack/recall.py:1-6` 읽음 |
| 발견10 | 회상 구획B 순서가 사용 기록에 따라 바뀐다. 지난 주입 뒤 바뀐 항목을 위로 올리고, 10번 주입했는데 열리지 않은 항목을 내린다. Graph Home을 지우면 회상 결과가 달라진다. 이것은 §0 규칙5("사용 기록이 순위에 영향을 주면 Vault로 옮긴다")에 어긋난다. | `src/vault_graph/context/pack/recall.py:33, 313-356, 404-417` 읽음 |
| 발견11 | Claude Code 훅을 설치하는 길이 없다. install은 스킬, `recall.sh`, router, map, MCP 항목만 넣는다. vault-graph에도 수집 실행 명령이 없다. `sessions capture` 자체는 있고, 같은 세션을 다시 불러도 새 턴만 덧붙인다. | `vault-builder:tools/vault_migration/installing.py:319-398` 읽음. `vault-builder:tools/vault_migration/`에서 `SessionStart\|PreCompact\|SessionEnd\|hooks` 검색 결과 없음. `vault-builder:tools/wiki/lib/session_capture.py:431-479` 읽음, 반복 호출 동작은 research 문서 3절 |
| 발견12 | Vault 종류를 바꾸는 명령이 없다. install은 Vault를 늘 `personal`로 넣는다. 소유자가 팀 Vault를 더하려면 `vault-map.json`을 손으로 고쳐야 한다. | `vault-builder:tools/vault_migration/installing.py:372, 383` 읽음 |
| 발견13 | Vault 쓰기 코드(`remember_service.py`)가 설정 기록 영역 M17(`operation/integration/`)에 들어 있다. VG-MOD에서 M17의 책임은 "명시적으로 요청한 MCP 등록·연결 설정·지침 설치"이고, "Vault 내용 수정"은 M17 경계 밖이다. 수정·폐기·제안을 같은 파일에 더하면 경계가 더 흐려진다. | `docs/design/specs/2026-10-15-vault-graph-modular-architecture-ko.md:70`, `tests/test_feature_import_direction.py:35, 41-54` 읽음 |

정리하면 다음 일곱 가지가 없다.

1. 여러 Vault 검색 결합과 결과 표시(발견1·2)
2. 기본 저장 Vault(발견3)
3. 수정·폐기(발견4~7)
4. 추론 사실 승인(발견8)
5. 수집 실행 시점(발견11)
6. 고정 회상(발견9)
7. 사용 기록과 순위의 분리(발견10)

모듈 경계도 새 기능을 받을 준비가 되어 있지 않다(발견13).

## 2. Intent

사용자는 Claude Code가 세션을 넘어 기억을 잃지 않기를 원한다. 지금 Claude Code 기본 기억은 매 세션 통째로 읽는 평평한 파일 몇 개이고, 대화 기록은 30일 뒤 지워진다(brief, 2026-11-02 사용자 원문 요지).

변경 뒤에 참이어야 하는 것:

1. 기억은 Vault에만 산다. vault-graph의 Graph Home을 지우고 다시 만들어도 기억이 하나도 사라지지 않고, 세션 시작 회상의 고정 기억과 기억 목록이 같다.
2. 프로젝트가 쓰는 Vault 여러 개(개인, 프로젝트, 팀, 앞으로 생길 종류)를 한 번에 찾고, 결과마다 어느 Vault의 어떤 종류인지 보인다.
3. 에이전트는 사용자가 말한 사실을 추가·수정·폐기할 수 있다. Vault 검사를 통과하면 바로 확정된다. 에이전트가 추론한 사실은 사람이 승인할 때까지 Vault 검토 대기열에 머물고, 승인 전에는 회상과 검색에 나오지 않는다.
4. 모든 쓰기는 Vault 자체 도구가 한다. vault-graph는 Vault 파일을 직접 만들거나 고치지 않는다.
5. 세션이 압축되거나 끝날 때 대화 원문이 Vault에 저장된다. vault-graph가 있으면 vault-graph가 그 시점을 받아 실행하고, 없어도 저장은 된다.
6. 세션 시작 때 고정한 기억이 Vault와 상관없이 맨 앞에 정해진 예산 안에서 들어온다.
7. 새 기능은 좁은 인터페이스를 가진 별도 모듈이다. vault-graph의 가져오기 방향 예외 0건과 순환 0건이 그대로 유지된다(사용자 추가 요구).
8. 두 저장소의 설계 문서가 구현과 같은 내용을 말한다(사용자 요구).

이 spec은 위 내용 중 다음을 사용자의 인터뷰 답(brief 1~7번)에서 그대로 가져왔다.

- 범위 (a)~(g) 전부
- 폐기 방식
- 사용 기록을 순위에서 빼는 것
- 수집 시점 PreCompact + SessionEnd
- 추론 승인 흐름
- 성공 기준 ①~⑥과 수동 확인 1회

나머지 세부는 [가정]으로 표시했다.

## 3. Non-goals

- 측정1(검색 품질, 한국어 `body_stem`)과 재측정. 이전 spec `2026-10-29-local-graph-memory-layer`의 작업13·14에 남긴다(brief 6번).
- 정리 스킬의 자동 기억 확정 규칙(요청7, 의존4)을 Vault 쪽에서 구현하는 일. 이 spec은 vault-graph가 직접 부르는 stated/inferred 경로만 만든다.
- claim 단위 대체 제외와 최신성 가중치(n차-1). frontmatter `peer`, `observed_at` 해석과 `get_profile`(n차-2).
- 사용 기록을 Vault로 옮기는 일. 이번에는 사용 기록이 순위에 영향을 주지 않도록 끊는다. 옮길 값이 생기지 않는다.
- 질문 기반 회상(MCP `recall`, UserPromptSubmit 훅, n차-8·n차-11).
- Vault 종류별 고정 우선순위나 종류에 따른 자동 저장 Vault 선택(결정12·13·15가 금지한다).
- 페이지 파일 삭제. 폐기는 status만 바꾸고 파일은 남긴다(brief 2번).
- vault-graph가 검토 대기열을 읽거나 승인하는 일. 승인은 사람이 Vault 명령으로 한다(brief 5번).
- `project-bindings.json`과 `vg vault add` 제거(n차-7).
- 세션 수집 대상 Vault 선택 규칙 변경. 수집은 지금처럼 Vault 도구가 role `project` Vault 하나를 고른다(`vault-builder:tools/wiki/lib/session_capture.py:431-479`).
- 이전 spec 브랜치를 push하거나 PR을 여는 일. 사람이 한다.

## 4. Design

### 4.1 두 저장소 사이의 계약 목록

vault-builder가 계약을 소유하고, vault-graph는 그 계약을 부르거나 읽기만 한다. 아래 계약1~7은 vault-builder 쪽이고, 4.3의 V1~V6은 vault-graph 쪽이다.

| 코드 | 계약 | 소유 | 쓰는 쪽 | 요청 대응 |
|---|---|---|---|---|
| 계약1 | publish-draft `--json` 결과와 종료 코드 | vault-builder (`tools/wiki`) | vault-graph 쓰기 어댑터, 계약4 | 요청4, 의존6 |
| 계약2 | 기억 frontmatter 선택 필드와 status `retired` | vault-builder (`tools/wiki`) | vault-graph 회상, 쓰기 draft | 요청6, 의존5 |
| 계약3 | frontmatter만 바꾸는 `patch-page` | vault-builder (`tools/wiki`) | vault-graph 폐기 draft | 새 요청 |
| 계약4 | 검토 유형 `memory-proposal`, `review propose`, 승인 시 발행 | vault-builder (`tools/wiki`) | vault-graph 추론 경로, 사람 | 새 요청(요청7의 일부) |
| 계약5 | `vault-map.json` `default_write_vault`, role 설정 명령, 외부 계약 문서 | vault-builder (`tools/vault_migration`) | vault-graph `vault_map.py`, router | 요청5 확장 |
| 계약6 | 사용자 범위 훅 실행기 `vault_hooks.py`와 install `--with-hooks` | vault-builder (`tools/vault_migration`) | Claude Code, vault-graph `vg hook` | 요청3, 의존1 |
| 계약7 | Vault 계약 버전 4와 마이그레이션 | vault-builder (`tools/vault_migration`, manifest) | 기존 Vault | A6 |

모든 Vault 명령은 Vault 루트를 작업 디렉터리로 하여 `<python> -I -B tools/wiki/cli.py ...`로 실행한다. 이 방식은 지금 remember의 호출 방식과 같다(`src/vault_graph/interface/composition/adapters/vault_publish_cli.py:36-43`). 시간 제한은 120초다.

### 4.2 vault-builder 쪽 계약 (vault-builder 저장소 소유)

#### 계약1 publish-draft `--json`

- 명령: `tools/wiki/cli.py publish-draft <draft_path> [--report [PATH]] [--json]`.
- `--json`이 없으면 지금 텍스트 출력과 종료 코드를 그대로 둔다.
- `--json`이 있으면 표준 출력에 JSON 객체 하나만 쓴다. 사람이 읽는 줄은 표준 오류로 보낸다. 객체의 필드는 다음과 같다.
  - `format`: `"vault-publish-result/v1"`.
  - `draft_version`: 읽은 draft의 `version`. 지금은 1이다.
  - `status`: `"published"` 또는 `"rejected"`.
  - `reason`: `null`(published일 때), `"lint-dirty-before"`, `"draft-invalid"`, `"human-locked"`, `"page-missing"`(patch 대상 없음), `"lint-failed-after"`, `"io-error"` 중 하나.
  - `written_paths`: Vault 기준 상대 경로 목록.
  - `messages`: 문자열 목록(lint 문제, 검증 오류 원문).
- 종료 코드: 0은 published, 1은 rejected다. 2는 인자 오류이며 argparse의 기존 동작이다. 오래된 Vault 도구가 `--json`을 모를 때도 2가 나온다.
- 모듈: 발행 로직을 `tools/wiki/cli.py:705-745`에서 새 모듈 `tools/wiki/lib/publish.py`로 옮긴다. 공개 함수는 `def publish_draft(root: Path, draft_path: Path, report_path: Path | None = None) -> PublishResult` 하나다. `cli.py`는 결과를 텍스트나 JSON으로 출력만 한다.
- 거부 이유 구분: 사람이 잠근 페이지는 `ValueError` 대신 그 하위 클래스 `HumanLockError`로 올린다(`tools/wiki/lib/draft.py:63-67`). 대상이 없는 patch는 `PatchTargetMissing`으로 올린다(`draft_patch.py:40-41`).
- 실패 시 원래 파일로 되돌리는 동작(`cli.py:720-733`)과 성공 뒤 탐색 지도를 다시 만드는 동작(`cli.py:744`)은 바꾸지 않는다.

#### 계약2 기억 frontmatter 선택 필드와 status `retired`

- 선택 필드(없어도 기존 페이지는 그대로 유효하다):
  - `memory_schema`: 문자열. 지금 허용값은 `vault-memory/v1` 하나다.
  - `pin`: 불리언. `true`면 세션 시작 회상 맨 앞에 넣는다.
  - `memory_kind`: `rule`, `correction`, `decision`, `preference` 중 하나.
  - `retired_reason`: 비어 있지 않은 문자열.
  - `retired_at`: ISO 날짜.
- lint 규칙(새 모듈 `tools/wiki/lib/memory_fields.py`, `def validate_memory_fields(page: Page) -> list[Issue]`, `lint_repo`에서 부른다):
  1. `pin`이나 `memory_kind`가 있으면 `memory_schema`도 있어야 한다.
  2. `memory_schema`가 모르는 값이면 오류다.
  3. `pin`은 불리언, `memory_kind`는 허용 목록 안이어야 한다.
  4. status `retired`면 `retired_reason`과 `retired_at`이 있어야 한다.
  5. `retired_reason`, `retired_at`은 status `retired`일 때만 둔다.
- `schema.py:49`의 `ALLOWED_STATUS`에 `retired`를 더한다. `retired`에는 `superseded_by`가 필요 없다. 대체가 있는 폐기는 지금처럼 `deprecated` + `superseded_by`다(brief 2번).
- Vault 검색, 지도, 지표, `memory_scan`처럼 status를 나열하는 Vault 도구는 `retired`를 `deprecated`와 같게 "현재 아님"으로 다룬다. 구현 때 status 목록이 있는 곳을 모두 찾아 확인한다(7절 위험4).

#### 계약3 frontmatter만 바꾸는 `patch-page`

- 지금은 `edits`가 비어 있으면 거부한다(`draft_patch.py:42-44`). 바꾼 뒤에는 `frontmatter`에 키가 하나 이상 있으면 `edits`가 없거나 빈 목록이어도 받는다. 둘 다 비어 있으면 지금처럼 거부한다.
- 폐기는 이 형식을 쓴다. patch는 적용하는 순간 현재 파일을 읽어 만들기 때문에(`draft_patch.py:49-80`), vault-graph가 본문을 다시 보낼 필요가 없다.

#### 계약4 검토 유형 `memory-proposal`

- `review.py:15`의 `ALLOWED_REVIEW_TYPES`에 `memory-proposal`을 더한다.
- 새 명령: `review propose --draft <draft.json> --summary <text> [--evidence REF]... [--related WIKI_PATH]... [--json]`.
  1. draft를 dry-run으로 검증한다(`apply_draft(..., dry_run=True)`). 저장소 전체 lint 검사는 하지 않는다. 승인할 때 계약1이 다시 검사한다.
  2. 검증에 실패하면 아무것도 쓰지 않고 종료 코드 1로 끝난다.
  3. 성공하면 두 파일을 만든다. 검토 항목 `scratch/review/<review_id>.md`(type `memory-proposal`, status `pending`)와, 같은 이름의 draft 사본 `scratch/review/<review_id>.draft.json`이다.
  4. 검토 항목 frontmatter에는 기존 필드에 더해 `draft`(draft 사본의 Vault 상대 경로), `target_path`(draft 대상 페이지), `target_hash`(제안 시점 대상 파일의 sha256, 새 페이지면 빈 문자열)를 둔다.
  5. `review_id`는 `<날짜>-memory-<draft sha256 앞 8자>`다. 지금 slug는 ASCII만 남겨 한국어 요약이 모두 `review`가 된다(`review.py:345-347`). 그래서 이 유형은 해시를 쓴다.
- `review propose --json` 출력은 JSON 객체 하나다.
  - `format`: `"vault-review-result/v1"`
  - `status`: `"proposed"` 또는 `"rejected"`
  - `review_id`, `review_path`, `draft_path`, `target_path`
  - `messages`
- 종료 코드: 0은 proposed, 1은 rejected다.
- `review resolve <path> --status accepted --resolution <text> [--json]`을 `memory-proposal`에 실행하면 다음 순서로 처리한다.
  1. 대상 파일의 현재 sha256을 `target_hash`와 비교한다. 다르면 "제안 뒤 페이지가 바뀜"으로 거부한다. 종료 코드 1, 항목은 `pending`으로 남는다.
  2. 붙은 draft를 계약1의 `publish_draft`로 발행한다.
  3. 발행되면 항목을 `accepted`로 바꾸고, resolution에 쓴 경로를 적는다.
  4. 발행이 거부되면 항목을 `pending`으로 두고 종료 코드 1로 끝난다.
- `--status rejected`는 지금처럼 상태만 바꾸고 `wiki/log.md`에 기록 한 줄을 남긴다. 기억 페이지는 바뀌지 않는다. draft 사본은 남긴다(감사 기록).
- 다른 검토 유형의 `resolve` 동작은 바꾸지 않는다.
- lint(`validate_review_queue`, `review.py:106-184`): `memory-proposal` 항목은 `draft` 파일이 `scratch/review/` 아래에 있어야 한다.
- 모듈: 새 모듈 `tools/wiki/lib/memory_proposal.py`에 공개 함수 두 개를 둔다.
  - `def propose(root: Path, draft_path: Path, summary: str, evidence: list[str], related: list[str]) -> ProposalResult`
  - `def accept(root: Path, review_path: Path, resolution: str) -> AcceptResult`
- 방향: `cli.py` → `memory_proposal` → (`publish`, `review`). `review.py`는 `memory_proposal`을 가져오지 않는다. `publish.py`는 `review`와 `memory_proposal`을 가져오지 않는다.

#### 계약5 `vault-map.json` 확장과 role 설정

- version은 2로 둔다. 선택 필드를 하나 더한다. 없으면 지금 동작과 같다(A1).
  - `projects.<id>.default_write_vault`: 문자열. 그 프로젝트 `vaults` 목록 안의 Vault 이름이어야 한다.
- `vaults.<name>.role`: 비어 있지 않은 문자열이다. 문서상 값은 `personal`, `project`, `team`이고 다른 값도 허용한다. 새 필드 `type`은 만들지 않는다(A1).
- 새 명령 두 개. 모듈은 `tools/vault_migration/map_settings.py`다.
  - `set-default-write --project <id> (--vault <name> | --clear)`
  - `set-role --vault <name> --role <role>`
  - 두 명령은 다른 필드를 보존하고, 원자적으로 바꿔 쓴다(임시 파일 후 이름 바꾸기).
- 기존 쓰기 코드(`installing.py:352-390`, `linking.py:60-72`)는 모르는 필드를 지우지 않는다. `unlink`로 기본 저장 Vault를 프로젝트에서 빼면 `default_write_vault`도 지운다.
- llm-wiki router는 새 필드를 무시한다. 읽기 형식 검사가 새 필드 때문에 실패하지 않아야 한다.
- 외부 계약 문서 `docs/contracts/vault-map-v2.md`를 새로 쓴다. 필드, 선택 필드, 프로젝트 찾기 규칙의 소유자(router `find_project`), "형식을 깨면 version을 올린다"는 규칙을 적는다. [가정: 파일 위치]

#### 계약6 훅 실행기와 설치

- 새 asset `tools/vault_migration/assets/vault-hooks/vault_hooks.py`. install이 `$HOME/.claude/vault-builder/vault_hooks.py`로 복사한다. router와 같은 폴더다.
- 하위 명령 두 개. 둘 다 표준 입력의 Claude Code 훅 JSON을 그대로 넘기고, 언제나 종료 코드 0으로 끝난다. 훅이 Claude Code 세션을 막지 않게 하기 위해서다.

| 하위 명령 | vg가 있을 때 | vg가 없거나 실패할 때 |
|---|---|---|
| `session-start` | `vg hook session-start`를 실행한다. 종료 코드 0이면 표준 출력을 그대로 내보낸다(빈 출력도 그대로). | `recall.sh`의 출력을 내보낸다. |
| `capture` | `vg hook capture`를 실행한다. 종료 코드 0이면 끝낸다. | `capture --direct`와 같은 일을 한다. |
| `capture --direct` | 사용하지 않는다(vg 쪽이 부른다). | 훅 `cwd`의 프로젝트에서 role `project` Vault 하나를 골라 그 Vault의 `tools/wiki/cli.py sessions capture --json`에 훅 JSON을 넘긴다. 고르는 규칙은 `session_capture.py:431-479`와 같다. |

- vg 찾기 순서: 환경 변수 `VAULT_GRAPH_BIN`, install 때 기록한 `$HOME/.claude/vault-builder/vault-hooks.json`의 `vg` 절대 경로, `PATH`의 `vg`. 셋 다 없으면 vg가 없는 것으로 본다. [가정]
- vg 경로로 실패한 뒤 직접 수집을 다시 해도 안전하다. `sessions capture`는 같은 세션의 새 턴만 덧붙이고 기존 파일을 덮어쓰지 않는다(research 3절, `session_capture.py:482-598`).
- install 선택 항목 `--with-hooks`. 새 모듈은 `tools/vault_migration/hooks.py`다.
  - `$HOME/.claude/settings.json`의 `hooks.SessionStart`, `hooks.PreCompact`, `hooks.SessionEnd`에 실행기를 부르는 항목을 하나씩 더한다. 명령은 `<python> -I $HOME/.claude/vault-builder/vault_hooks.py <하위 명령>`이다.
  - 다른 훅 항목은 보존한다. 같은 항목이 있으면 바꾸지 않는다.
  - uninstall은 실행기 경로를 담은 항목만 지운다.
  - `--with-hooks`가 없으면 settings.json을 읽지도 쓰지도 않는다.
- 수집 훅 시간 제한: PreCompact와 SessionEnd 항목에 `timeout` 60초를 둔다. [가정]

#### 계약7 Vault 계약 버전 4

- `tools/wiki/lib/vault_manifest.py:94`의 `MANIFEST_CONTRACT_VERSION`을 3에서 4로 올린다.
- 계약1~4의 `tools/wiki` 변경은 기존 Vault에 마이그레이션 audit → apply로 전달한다(A6).
- 계약 4 미만 Vault에 vault-graph가 쓰기를 부르면 `--json`을 몰라 종료 코드 2가 나온다. vault-graph는 이 경우를 `error`와 "Vault 도구를 계약 4로 마이그레이션하라"로 보고한다(6절).

### 4.3 vault-graph 쪽 설계 (vault-graph 저장소 소유)

#### V1 모듈 배치

| 모듈 | 영역 | 공개 표면 | 바뀌는 이유 |
|---|---|---|---|
| `operation/memory/` (새 패키지) | 새 영역 M18 `memory_write` | 아래 V3 | Vault 기억 쓰기 정책 |
| `operation/memory/memory_requests.py` | M18 | `RememberRequest`, `UpdateRequest`, `RetireRequest`, `MemoryWriteResult`, `Basis = Literal["stated", "inferred"]` | 요청·응답 형식 |
| `operation/memory/memory_target.py` | M18 | `def choose_write_vault(vault: str \| None, cwd: Path \| None, vault_map: VaultMapReader) -> MappedVault \| VaultRequired \| WriteRefusal` | 결정12 |
| `operation/memory/memory_drafts.py` | M18 | `build_remember_draft`, `build_update_draft`, `build_retire_draft` (순수 함수) | Vault draft 형식 |
| `operation/memory/memory_ports.py` | M18 | `class VaultWriter(Protocol)`: `publish(vault_root, draft_path, *, timeout_s) -> WriteOutcome`, `propose(vault_root, draft_path, *, summary, evidence, timeout_s) -> WriteOutcome`. `class VaultPageReader(Protocol)`: `read(vault_root, path) -> PageText \| None` | 포트 |
| `operation/memory/memory_write_service.py` | M18 | `class MemoryWriteService`: `remember`, `update`, `retire` | 흐름 조립, Vault별 잠금 |
| `operation/integration/remember_service.py` | 삭제 | M18로 옮긴다 | 발견13 |
| `context/pack/recall_pins.py` (새 파일) | M08 | `def pin_block(entries, *, max_tokens) -> PinBlock` | 구획A |
| `context/pack/recall.py` | M08 | 시그니처 그대로 | 구획A 연결, 사용 기록 순위 제거 |
| `context/memory/project_memory.py` | M10 | `STALE_STATUSES`에 `retired` 추가 | 계약2 |
| `operation/integration/vault_map.py` | M17 | 기존 표면 + `default_write_vault` 읽기 | 계약5 |
| `project/context/project_binding_reader.py` | M12 | `MappedProjectMatch.default_write_vault: MappedVault \| None` | 계약5 |
| `interface/composition/vault_labels.py` (새 파일) | COMPOSITION | `VaultLabel(name, role)`, `def vault_labels(vault_map, catalog) -> Mapping[str, VaultLabel]` | 결과 표시 |
| `interface/composition/query_scope_resolution.py` | COMPOSITION | `def default_query_vault_ids(cwd: Path, *, vault_map, vault_catalog) -> tuple[str, ...] \| None` | A7 |
| `interface/composition/adapters/vault_publish_cli.py` | COMPOSITION | `VaultWriter` 구현(계약1 `--json`, 계약4 `review propose --json`) | 텍스트 파싱 제거 |
| `interface/composition/adapters/vault_page_reader.py` (새 파일) | COMPOSITION | `VaultPageReader` 구현(읽기만) | 수정 draft의 현재 페이지 |
| `interface/composition/adapters/vault_capture_cli.py` (새 파일) | COMPOSITION | `def run_capture(hook_json: bytes, *, launcher: Path, timeout_s: float) -> CaptureOutcome` | 계약6 `capture --direct` 호출 |
| `interface/cli/hook_commands.py` | COMPOSITION | `vg hook capture` 추가 | 수집 시점 |
| `interface/mcp/mcp_tools.py` 등 | COMPOSITION | V3·V2의 도구 입출력 | 공개 표면 |

- 방향 표(`tests/test_feature_import_direction.py`) 변경
  - `_AREAS`에 `"operation/memory/": "M18"`를 더한다.
  - `_ALLOWED`에 `"M18": frozenset({"M01", "M12"})`를 더한다. M12의 `VaultMapReader`와 `MappedVault`를 쓰기 때문이다.
  - `_PLANNED_MODULES`와 `_AREAS`에서 `remember_service.py` 줄을 지우고 새 파일을 넣는다.
  - 어떤 영역도 M18을 가져오지 않는다. M18을 조립하는 것은 구성 지점뿐이다.
  - `_KNOWN_VIOLATIONS`는 빈 집합, `_KNOWN_VIOLATION_CEILING`은 0으로 둔다.
- 수집에는 새 기능 영역을 만들지 않는다. vault-graph는 수집 대상과 내용을 정하지 않고 실행 시점만 정한다. 판단할 정책이 없으므로 전송 계층(`hook_commands.py`)과 어댑터 하나로 끝낸다(5절 결정S4).
- Vault 이름·종류 표시는 구성 지점에서 붙인다. 검색 DTO(`RetrievalResult`, M05)는 바꾸지 않는다. M05가 `vault-map.json`을 알 필요가 없게 하기 위해서다.

#### V2 여러 Vault 검색과 결과 표시 (범위 a)

- 검색 범위를 정하는 순서(MCP `search_vault`, `ask_vault`, `build_context_pack`, CLI `vg search`·`vg ask`·`vg context`, HTTP 검색)
  1. 요청에 `scope`(`vault_ids` 또는 `all_vaults`)가 있으면 지금처럼 그것을 쓴다.
  2. 없으면 `cwd`로 프로젝트를 찾는다. 찾으면 그 프로젝트에 연결되고 Graph Home에 등록된 Vault 전부를 쓴다(`resolve_project_vaults`, `query_scope_resolution.py:38-70`).
  3. 프로젝트를 찾지 못하면 지금처럼 활성 Vault 하나를 쓴다.
- `cwd`를 정하는 방법
  - MCP 세 도구는 선택 입력 `cwd: str | None`을 받는다. 없으면 MCP 서버 프로세스의 작업 디렉터리를 쓴다(9절 질문2).
  - 2026-11-02 의도 검수 반영(F4): `find_related`, `get_decision_trace`, `summarize_project_memory`, `get_open_questions`, `get_recent_changes`도 같은 선택 입력 `cwd`와 위 1~3단계 범위 규칙을 쓴다. 전에는 활성 Vault 하나만 읽어서, 이 컴퓨터에서 다른 프로젝트 Vault를 읽었다. 이 다섯 도구는 `ask_vault`처럼 프로젝트에 검색할 Vault가 하나도 없으면 빈 결과 대신 오류를 낸다.
  - CLI는 프로세스 작업 디렉터리를 쓴다.
  - HTTP는 선택 필드 `cwd`를 받는다. 없으면 3단계(활성 Vault)로 간다.
- 결합은 기존 `fuse_candidates`(`src/vault_graph/retrieval/search/candidate_ranking.py:26-51`)가 만든 관련도 순 한 목록을 그대로 쓴다. 종류 간 고정 우선순위는 두지 않는다(결정13).
- 결과 표시: 검색 결과 JSON의 각 결과에 `vault_name`과 `vault_role`을 더한다.
  - `vault_labels`가 Graph Home catalog의 Vault 경로와 `vault-map.json` Vault 경로를 실제 경로로 맞춰 채운다.
  - map에 없는 Vault는 두 값이 `null`이다.
  - 기존 필드는 바꾸지 않는다.
  - CLI 텍스트 출력은 결과 줄 앞에 `[<vault_name>·<vault_role>]`을 붙인다.
- 코드는 role 값으로 분기하지 않는다(결정15). role은 표시용 문자열로만 지나간다.
- 폐기 페이지: frontmatter status가 `retired`인 페이지의 결과는 기본 검색 결과에서 뺀다(9절 질문3 권장안). 결합 뒤 M05가 메타데이터 읽기 포트의 문서 frontmatter로 거른다. 순서를 바꾸는 변경이므로 VG-MOD INV-05 예외로 `docs/DECISIONS.md`에 기록한다. `deprecated`는 지금처럼 남긴다.

#### V3 기억 쓰기: 추가·수정·폐기와 기본 저장 Vault (범위 b, c, d)

MCP 도구:

- `remember(title, kind, body, evidence, basis, cwd=None, vault=None, pin=False, memory_kind=None)`.
  - 기존 도구에 `basis`(필수), `pin`, `memory_kind`를 더한다.
- `update_memory(path, body, evidence, basis, vault=None, cwd=None, title=None, pin=None, memory_kind=None)`. 새 도구다.
- `retire_memory(path, reason, basis, vault=None, cwd=None, replaced_by=None)`. 새 도구다.
- MCP 도구는 12개에서 14개가 된다(9절 질문1).
- 2026-11-02 의도 검수 반영(F7, F8):
  - 세 도구는 `cwd`가 없으면 검색 도구처럼 MCP 서버 프로세스의 작업 디렉터리를 `cwd`로 쓴다. 전에는 `cwd`가 없으면 프로젝트를 정하지 않고 map 전체에서 Vault를 찾아, 다른 프로젝트 Vault에 쓸 수 있었다.
  - 도구 스키마는 `basis`(`stated`, `inferred`), `kind`(`decision`, `system`), `memory_kind`(`rule`, `correction`, `decision`, `preference`)의 허용 값을 enum으로 보인다.

응답 `MemoryWriteResult`의 필드:

- `status`: `published`, `proposed`, `rejected`, `vault_required`, `error` 중 하나.
- `vault`, `vault_role`
- `written_paths`
- `review_path`: proposed일 때만 있다.
- `candidates`: vault_required일 때 `{name, role}` 목록.
- `messages`

저장 Vault 고르기(`choose_write_vault`, 결정12):

1. `vault`가 있으면 그 이름을 찾는다. `cwd`의 프로젝트가 정해지면 그 프로젝트의 연결 Vault 안에서만 찾는다(발견3 수정). 프로젝트가 정해지지 않으면 map 전체에서 찾는다.
2. `vault`가 없으면 프로젝트의 `default_write_vault`를 쓴다.
3. 기본 저장 Vault가 없고 연결 Vault가 하나면 그것을 쓴다.
4. 둘 이상이면 쓰지 않고 `vault_required`와 후보를 돌려준다.
5. `memory_kind`나 role로 고르지 않는다.

수정·폐기 대상 페이지 찾기(A2):

- `path`는 Vault 상대 경로다(`wiki/...md`).
- `vault`가 없으면 프로젝트 연결 Vault 중 그 경로가 있는 Vault를 찾는다. 정확히 하나면 그것을 쓰고, 0개면 `rejected`, 둘 이상이면 `vault_required`를 돌려준다. 기본 저장 Vault 규칙은 새 페이지에만 쓴다. 수정·폐기는 페이지가 이미 있는 Vault가 대상이기 때문이다.

draft(모두 vault-graph가 에이전트 입력과 실행 날짜만으로 결정적으로 만든다, 결정7):

| 동작 | Vault draft | frontmatter |
|---|---|---|
| 추가 | `upsert-page`. 지금 `build_draft`(`remember_service.py:167-204`)와 같다. 본문 Evidence 절의 `Status:`에 `basis`를 적는다. 같은 경로가 있으면 publish 전에 `rejected`를 돌려준다(지금과 같음). | `pin`이나 `memory_kind`가 있으면 `memory_schema: vault-memory/v1`과 함께 넣는다. |
| 수정 | `upsert-page`. `VaultPageReader`로 현재 페이지를 읽는다. frontmatter는 현재 값을 유지하고 `updated`, 그리고 준 값(`title`, `summary`=title, `pin`, `memory_kind`)만 바꾼다. 본문은 에이전트가 준 `body`와 Evidence 절로 통째로 바꾼다. 페이지가 없으면 `rejected`다. | 위와 같음 |
| 폐기(대체 없음) | 계약3 frontmatter만 바꾸는 `patch-page`. `log`에 폐기 기록 한 줄을 둔다. | `status: retired`, `retired_reason: <reason>`, `retired_at: <오늘>` |
| 폐기(대체 있음) | 같은 `patch-page`. `replaced_by` 페이지가 같은 Vault에 있어야 한다. | `status: deprecated`, `superseded_by: [<대상>]` |

`basis`별 경로(brief 5번):

- `stated`: `VaultWriter.publish`가 계약1을 실행한다. 결과는 `published` 또는 `rejected`다.
- `inferred`: `VaultWriter.propose`가 계약4 `review propose`를 실행한다. 결과는 `proposed`이고 `review_path`가 붙는다. `messages`에는 사람이 실행할 승인 명령 한 줄(`review resolve <review_path> --status accepted --resolution "<사유>"`)을 넣는다.
- vault-graph는 `scratch/review/`를 색인하지 않는다(`DEFAULT_CONTENT_SCOPES`, `docs/SPEC.md` §4). 그래서 승인 전에는 회상과 검색에 나오지 않는다.

동시 실행과 경쟁:

- 같은 Vault에 대한 쓰기는 한 프로세스 안에서 하나씩 실행한다. 지금 `_vault_lock`(`remember_service.py:70-77`)을 옮겨 세 동작이 같이 쓴다.
- 수정은 잠금 안에서 페이지를 읽은 sha256을 publish 직전에 다시 확인한다. 다르면 `rejected`("페이지가 바뀌었다, 다시 읽어라")다.
- 사람이 잠근 페이지와 잠긴 절은 Vault가 거부하고(`reason: human-locked`), vault-graph는 그 결과를 그대로 `rejected`로 돌려준다.

어댑터(`vault_publish_cli.py`):

- 계약1·계약4의 `--json` 출력만 읽고 텍스트를 해석하지 않는다.
- 종료 코드 2와 표준 오류의 `unrecognized arguments`는 "Vault 도구가 계약 4 미만"으로 바꿔 `error`를 돌려준다.
- 표준 출력이 JSON이 아니면 `error`다.

#### V4 세션 시작 회상: 고정 기억과 사용 기록 분리 (범위 f, g)

- 구획A(고정 기억): 프로젝트 범위 안 `wiki/` 페이지 중 frontmatter `pin: true`이고 현재 상태인 것(`STALE_STATUSES`와 `retired` 제외)을 넣는다. Vault와 상관없이 구획B보다 먼저 넣는다(결정14).
  - 항목은 두 줄이다. 첫 줄은 `- [m:<id>] <memory_kind 또는 type> · <제목> (<위치>)`, 둘째 줄은 frontmatter `summary`다. `summary`가 없거나 제목과 같으면(`remember`는 제목을 그대로 넣는다) 둘째 줄은 본문 앞부분 60토큰이다. 제목 줄과 `## Evidence` 절은 빼고, 잘리면 `…`를 붙인다(2026-11-03 F10).
  - 순서: `updated` 내림차순, 같으면 경로순.
  - 예산 400토큰. 넘치면 뒤에서부터 줄이고 "N개 생략" 한 줄을 둔다.
  - 구획A에 넣은 페이지는 구획B에 다시 넣지 않는다.
  - 제목은 `## 고정 기억`이다.
- 구획B 순서: 모든 연결 Vault 페이지를 합쳐 `updated` 내림차순, 같으면 (Vault 이름, 경로)순으로 정렬한다. 사용 기록으로 순서를 바꾸는 두 동작을 지운다(`recall.py:410-417`의 "바뀐 항목 올리기"와 "열리지 않은 항목 내리기", `DEMOTE_AFTER_INJECTIONS`).
- 구획D(2026-11-03 F11): `startup`·`clear`·`compact`에서 연결 Vault의 `scratch/review/` 안 `type: memory-proposal`, `status: pending` 항목이 있으면 `- 승인을 기다리는 추론 제안: <Vault 이름> N개. 확인은 그 Vault 폴더에서 `python3 tools/wiki/cli.py review list --status pending`` 한 줄을 더한다. 검토 대기열은 색인하지 않으므로 항목 frontmatter를 직접 읽기만 한다(`interface/composition/adapters/vault_review_queue.py`). 읽지 못하면 경고 한 줄을 내고 줄을 뺀다.
- 구획B 제외(2026-11-02 의도 검수 반영, F3): frontmatter `type`이 `index`, `log`, `map`, `overview`인 페이지는 구획B에 넣지 않는다(`NAVIGATION_PAGE_TYPES`). Vault가 발행할 때마다 다시 쓰는 탐색 페이지라서 기억이 아니다. Vault 종류(role)가 아니라 페이지 `type`으로 거른다(결정15). 고정(`pin: true`)한 탐색 페이지는 구획A에 그대로 나온다.
- 구획C: `retired`를 `NOTICE_STATUSES`에 더한다. 알림 줄은 "옛 제목 → 폐기됨: <retired_reason> (날짜)"다.
- 사용 기록 남김: `injected`, `fetched` 기록은 계속 쓴다. 읽는 곳은 구획C 알림 중복 방지(`_History.noticed`와 기준 실행 찾기) 하나다. 측정용으로 남긴다(brief 3번).
- 결과: Graph Home을 지우고 다시 만들어도 구획A·B는 바이트 단위로 같다. 구획C는 중복 방지 기록이 사라져 이미 알린 항목이 한 번 더 나올 수 있다. brief 3번의 "사용 기록은 알림 중복 방지에만 쓴다"와 맞는다.
- 위치 표기: Vault가 둘 이상이면 지금처럼 `vault_id:경로`를 쓰되, `vault_labels`로 얻은 Vault 이름이 있으면 이름을 쓴다.

#### V5 수집 실행 시점 (범위 e)

- CLI `vg hook capture [--vault-map PATH] [--timeout S]`. 표준 입력으로 Claude Code PreCompact 또는 SessionEnd 훅 JSON을 받는다.
- 동작: `vault-map.json`이 있는 폴더의 `vault_hooks.py`(계약6)를 `capture --direct`로 실행하고, 훅 JSON을 그대로 넘긴다. 결과 JSON(`sessions capture --json`의 `status`, `vault`, `path`)을 표준 오류에 한 줄로 요약한다.
- 종료 코드: 0은 실행기가 끝났음(written, no-new-turns, skipped 모두)이다. 3은 실행기를 찾지 못했거나 시간이 넘었음이다. 훅 실행기는 0이 아니면 직접 수집한다(계약6).
- vault-graph는 수집 대상 Vault를 고르지 않는다. role로 분기하지도 않는다. 수집 직후 색인은 하지 않는다(9절 질문4).
- Graph Home에는 아무것도 쓰지 않는다.
- 2026-11-02 의도 검수 반영(F1): 새 세션 파일과 새 기억 페이지는 `vg index`를 기다리지 않는다.
  - `vg hook session-start`가 회상 전에, 이미 색인된 연결 Vault에서 바뀐 파일만 메타데이터와 그래프로 다시 색인하고 새 세대를 발행한다(`interface/composition/recall_index_refresh.py`). 임베딩은 만들지 않는다. 새 조각의 벡터는 다음 `vg index`가 만든다. 그 전까지 의미 검색은 그 조각을 찾지 못하고, 색인 상태는 벡터가 오래됐다고 보고한다.
  - 시간 한도는 기본 5초이고 `--refresh-budget S`로 바꾼다. 0이면 하지 않는다. 한도를 넘거나 실패하면 아무것도 발행하지 않고 표준 오류에 경고 한 줄을 낸 뒤 기존 색인으로 회상한다. 훅은 이 때문에 실패하지 않는다. `vg index`로 한 번도 발행하지 않은 Graph Home에서는 하지 않는다.
  - 2026-11-02 재검수 반영(발견1·3): 갱신이 훅 실행기의 20초 제한을 넘지 않도록 범위를 제한한다.
    - 바뀐 파일 찾기는 파일을 파싱하지 않고 SHA-256만 색인 값과 비교하며, 파일 하나를 볼 때마다 시간 한도를 확인한다. 한도 안에 다 보지 못하면 갱신을 건너뛴다.
    - 바뀌거나 지운 파일이 200개(`MAX_QUICK_REFRESH_FILES`)를 넘으면 갱신을 건너뛴다.
    - 다른 실행이 세대 발행 잠금을 쥐고 있으면 최대 1초(`MAX_LOCK_WAIT_S`)만 기다리고, 그래도 비지 않으면 갱신을 건너뛴다.
  - 2026-11-02 3차 검수 반영(발견8): 갱신은 바뀌거나 지운 파일만 읽어 메타데이터에 쓴다(`IndexService.run_apply_paths`). 그래프는 발행에 필요해서 Vault 전체로 다시 맞춘다. 그래프와 발행은 색인된 문서 수만큼 시간이 들므로, 다음 두 경우에는 쓰기 전에 갱신을 건너뛴다.
    - 연결 Vault에 색인된 문서가 1,500개(`MAX_QUICK_REFRESH_DOCUMENTS`)를 넘는다.
    - 같은 Vault의 최근 두 번의 갱신 시간을 오늘 문서 수로 늘려 잡은 값이 둘 다 남은 시간보다 길다. 갱신 시간은 Graph Home `logs/quick-refresh-times.json`에 Vault 묶음마다 최근 두 번을 남기고, 하루가 지난 기록은 쓰지 않는다. 한 번만 느린 기록은 다음 갱신을 막지 않는다(2026-11-03 발견12).
    - 그래서 1,500개가 넘는 Vault에서는 MCP 밖에서 바뀐 파일(세션 원문 등)이 다음 세션 시작의 백그라운드 `vg index`로 색인되고, 그다음 세션 회상부터 나온다.
    - 메타데이터 DB에 `chunks(blob_hash)` 인덱스를 더했다. 쓰기 권한으로 열 때 기존 DB에도 더한다.
  - 2026-11-02 3차 검수 반영(발견10): 바뀐 파일 찾기가 끝나면, 갱신이 아무것도 쓰기 전에 분리된 백그라운드 프로세스 하나를 띄운다(`hook_commands.start_catch_up_index`). 그래서 훅 실행기가 나중에 훅을 멈춰도 이 프로세스는 남는다. 훅은 이 프로세스를 기다리지 않는다.
    - 이 프로세스는 파이프로 훅의 갱신이 끝나기를(또는 훅이 사라지기를) 기다린 뒤 일반 `vg index --vault-id <id>`(임베딩 포함)를 차례로 실행한다. 대상은 바뀐 파일이 있는 연결 Vault(찾기가 시간 안에 끝나지 않았으면 연결 Vault 전부)와, 벡터가 오래됐거나 없는 나머지 연결 Vault다. 그래서 중간에 죽은 백그라운드 색인은 다음 세션 시작에서 다시 실행된다.
    - 이 프로세스는 살아 있는 동안 `<graph home>/logs/session-start-index.lock`에 flock을 쥔다. 잠금이 잡혀 있으면 훅은 새로 띄우지 않으므로, 세션이 여러 번 시작돼도 백그라운드 색인이 겹쳐 뜨지 않는다. `logs/session-start-index.pid`의 프로세스 ID는 참고용이다.
    - 출력은 `<graph home>/logs/session-start-index.log`에 덧붙인다. 1MB를 넘으면 새로 쓴다.
    - 프로세스를 띄우지 못하면 경고 한 줄만 내고 훅은 그대로 성공한다.
  - MCP 쓰기 도구가 `published`를 돌려주면, 서버가 그 Vault의 증분 색인(`vg index --vault-id`와 같은 동작)을 백그라운드 스레드로 시작하고, 끝나면 검색 서비스를 다시 연다(`McpServiceFactory.start_background_index`). 도구 결과는 색인을 기다리지 않는다. 색인을 시작하면 결과 `messages`의 "`vg index`를 실행하라" 안내가 "백그라운드로 색인 중" 안내로 바뀐다. 색인 실행은 한 프로세스에서 한 번에 하나다.
  - 2026-11-02 3차 검수 반영(발견7): MCP 도구와 페이지·문서·그래프 리소스는 같은 서비스 보관 객체(`CurrentMcpServices`)를 쓴다. 읽을 때마다 활성 세대 id를 확인하고, 바뀌었으면 서비스를 다시 연다. 그래서 이전 세대 폴더가 지워진 뒤에도 기억 본문이 열린다.

#### V6 `vault-map.json` 읽기 확장

- `vault_map.py`의 형식 검사(`_shape_problem`, 179-203행)는 모르는 필드를 이미 허용한다. 읽어서 확인했다. llm-wiki router의 검사(`vault-builder:tools/vault_migration/assets/llm-wiki-router/llm_wiki_router.py:113-121`)도 같다.
- `default_write_vault` 처리:
  - 문자열이 아니거나 그 프로젝트 `vaults`에 없으면 그 필드만 무시하고 경고한다. 파일 전체를 버리지 않는다.
  - `MappedProjectMatch.default_write_vault`에 해당 `MappedVault`를 담는다.
- `vg status`는 프로젝트별 기본 저장 Vault를 보인다.

### 4.4 vault-builder 모듈 방향

새 모듈은 아래 방향만 가진다. 역방향과 순환은 없다.

- `tools/wiki/cli.py` → `lib/publish.py`, `lib/memory_proposal.py`, `lib/review.py`, `lib/memory_fields.py`(lint 경유)
- `lib/memory_proposal.py` → `lib/publish.py`, `lib/review.py`, `lib/draft.py`
- `lib/publish.py` → `lib/draft.py`, `lib/lint.py`, `lib/maps.py`
- `lib/lint.py` → `lib/memory_fields.py`
- `lib/memory_fields.py` → `lib/schema.py`, `lib/frontmatter.py`만
- `tools/vault_migration/cli.py` → `map_settings.py`, `hooks.py`. `hooks.py`와 `map_settings.py`는 서로 가져오지 않는다.

새 테스트 파일:

- `tests/test_publish_json.py`, `tests/test_memory_fields.py`, `tests/test_memory_proposal.py`
- `builder_tests/test_map_settings.py`, `builder_tests/test_hooks_install.py`, `builder_tests/test_vault_hooks_launcher.py`
- `tests/test_wiki_lib_import_direction.py`: 위 방향을 AST로 검사한다. [가정: vault-builder에 같은 검사가 아직 없다]

### 4.5 작업 단계

선행 열의 단계가 끝나야 시작한다. 같은 선행을 가진 단계는 나란히 할 수 있다. 각 단계는 독립 커밋으로 끝내고, 그 저장소의 전체 테스트를 통과해야 한다. vault-builder는 `bash scripts/release_gate.sh`와 `python3 -m unittest builder_tests.test_llm_wiki_router`, vault-graph는 `pytest`다.

| 단계 | 저장소 | 내용 | 선행 | 나란히 |
|---|---|---|---|---|
| 0 | vault-graph | `docs/SPEC.md` §0 결정12~15, `docs/DECISIONS.md` 2026-11-02, 이 spec 커밋(brief 7번) | 없음 | B1~B5, G1과 |
| B1 | vault-builder | 계약1 `publish.py` 추출과 `--json` | 없음 | B2, B4, B5 |
| B2 | vault-builder | 계약2 frontmatter 필드와 `retired`, 계약3 frontmatter만 바꾸는 patch | 없음 | B1, B4, B5 |
| B3 | vault-builder | 계약4 `memory-proposal` | B1, B2 | B4, B5 |
| B4 | vault-builder | 계약5 map 필드, `set-default-write`, `set-role`, 계약 문서 | 없음 | B1, B2, B5 |
| B5 | vault-builder | 계약6 실행기와 `--with-hooks` | 없음 | B1, B2, B4 |
| B6 | vault-builder | 계약7 계약 버전 4와 마이그레이션 | B1, B2, B3 | B5 |
| B7 | vault-builder | 문서 갱신(8절 A-26) | B1~B6 | G 단계와 |
| G1 | vault-graph | V1 M18 패키지 생성, `remember_service.py` 이동, 방향 표 갱신(동작 변경 없음) | 0 | B 단계와 |
| G2 | vault-graph | V4 중 사용 기록 순위 제거와 `retired` 상태 반영 | 0 | B 단계, G1과 |
| G3 | vault-graph | V6, V2(범위와 표시) | G1, B4 | G4, G5 |
| G4 | vault-graph | V3 stated 경로(추가·수정·폐기, 기본 저장 Vault, `--json` 어댑터) | G1, G3, B1, B2 | G5 |
| G5 | vault-graph | V4 구획A | G2, B2 | G4 |
| G6 | vault-graph | V3 inferred 경로 | G4, B3 | G7 |
| G7 | vault-graph | V5 `vg hook capture` | B5 | G6 |
| G8 | vault-graph | 시나리오 ①~⑥ E2E와 문서 갱신(8절 A-25) | G2~G7, B6 | B7과 |
| G9 | 두 저장소 | 실제 세션 수동 확인 1회 | G8, B7 | 없음 |

vault-builder 계약 단계(B1~B6)는 그 계약을 쓰는 vault-graph 단계보다 먼저 커밋한다. G3~G7은 vault-builder 코드를 부르지 않는 단위 테스트(가짜 포트)로 먼저 만들 수 있다. 다만 계약 문서(이 spec 4.2)를 바꾸지 않는 범위에서만 그렇게 한다.

## 5. Decisions

표기: [사용자]는 사람이 인터뷰에서 정한 것(brief 번호), [가정]은 작성자가 정한 것이며 spec gate에서 확인한다. 이 spec에서 새로 정한 것은 `결정S`로 시작한다. 결정12~15는 `docs/SPEC.md` §0의 번호를 그대로 쓴다.

1. [사용자, brief 1번] 범위 (a)~(g) 전부를 단계별로 한다. 이유: 일곱 가지가 모두 §0 규칙의 빈 곳이다(1절).
2. [사용자, brief 7번] 결정12~15를 그대로 채택하고 첫 커밋(단계0)에 넣는다.
3. [사용자, brief 2번] 대체 없는 폐기는 새 status `retired`와 필수 `retired_reason`으로 한다. 대체가 있으면 `deprecated` + `superseded_by`. 파일은 지우지 않는다. 이유: 이력이 Vault에 남고, 지금 lint 규칙(`lint.py:433-441`)을 깨지 않는다.
4. [사용자, brief 3번] 사용 기록은 순위에 영향을 주지 않는다. 측정과 알림 중복 방지에만 쓴다. 이유: §0 규칙5와 시나리오⑥.
5. [사용자, brief 4번] 수집 시점은 PreCompact와 SessionEnd다. vg가 있으면 vg가 받아 capture를 실행하고, 없으면 훅이 capture를 직접 부른다.
6. [사용자, brief 5번] 추론 사실은 `memory-proposal` 검토 항목과 draft로 보낸다. 사람이 `review resolve --status accepted`로 승인하면 Vault가 발행한다. vault-graph는 `scratch/review/`를 색인하지 않는다.
7. [사용자, brief 6번] 성공 기준은 시나리오 ①~⑥ 자동 E2E와 실제 세션 수동 확인 1회다.
8. [사용자, brief 요구] 새 기능은 별도 모듈이고, 방향 예외 0건과 순환 0건을 유지한다. 두 저장소 문서를 개발과 함께 갱신한다.
9. [가정 A1] 기본 저장 Vault는 프로젝트 항목의 선택 필드 `default_write_vault`다. version 2를 유지한다. 종류는 기존 `role`을 쓴다. 이유: 두 읽기 코드가 모르는 필드를 이미 허용하므로(V6) 버전을 올릴 필요가 없다.
10. [가정 A2] 수정은 `upsert-page`, 대상은 Vault 상대 경로다. 잠긴 페이지는 Vault가 거부하고 vault-graph는 그대로 보고한다.
11. [가정 A3] vault-graph는 publish-draft의 텍스트 대신 계약1 JSON을 읽는다. 이유: 지금 어댑터는 문구가 바뀌면 조용히 틀린다(발견7).
12. [가정 A4] `pin`, `memory_kind`, `memory_schema`는 선택 필드다. 기존 페이지는 그대로 유효하다.
13. [가정 A5] 훅 설치는 install의 선택 항목 `--with-hooks`다.
14. [가정 A6] Vault 쪽 변경은 `tools/wiki` 템플릿에 넣고 계약 버전 4 마이그레이션으로 기존 Vault에 전한다.
15. [가정 A7] 검색 기본 범위는 `cwd`의 프로젝트 연결 Vault 전부, 프로젝트가 없으면 활성 Vault다.
16. [가정 A8] vault-graph는 이 브랜치 위에, vault-builder는 `feat/jh/vault-graph-requests` 위에 쌓고 PR을 따로 연다.
17. 결정S1 [가정] Vault 기억 쓰기를 새 영역 M18 `operation/memory/`로 옮긴다. 허용 방향은 M01, M12다. 이유: M17의 책임은 설정 기록이고 Vault 내용 수정은 경계 밖이다(발견13). 추가·수정·폐기·제안을 한 영역에 모으면 바뀌는 이유가 하나가 된다. 대안(M17에 그대로 둠)은 9절 질문7.
18. 결정S2 [가정] Vault 이름·종류 표시는 구성 지점의 `vault_labels`가 붙인다. 검색 DTO는 그대로 둔다. 이유: M05가 `vault-map.json`에 의존하지 않는다.
19. 결정S3 [가정] 수정과 폐기는 별도 MCP 도구 `update_memory`, `retire_memory`다. 이유: 도구마다 필수 입력이 달라 스키마가 단순하다. 대안은 9절 질문1.
20. 결정S4 [가정] 수집에는 새 기능 영역을 만들지 않는다. 이유: vault-graph는 시점만 정하고 대상·내용 판단이 없다. 정책이 없는 영역은 얕은 모듈이 된다(AGENTS.md "Deep Modules").
21. 결정S5 [가정] 세 쓰기 도구 모두 `basis`(`stated`, `inferred`)가 필수이고 기본값이 없다. 이유: 기본값이 `stated`면 에이전트가 추론을 확정 사실로 쓸 수 있다. 대안은 9절 질문6.
22. 결정S6 [가정] 폐기는 frontmatter만 바꾸는 `patch-page`(계약3)로 한다. 이유: 적용 시점의 현재 파일을 쓰므로 본문을 다시 보내지 않고 경쟁이 줄어든다. 대안은 9절 질문5.
23. 결정S7 [가정] `memory-proposal`의 `review_id`는 draft 해시로 만들고, 승인 때 `target_hash`가 다르면 거부한다. 이유: 한국어 요약 slug가 모두 `review`가 되는 문제(`review.py:345-347`)와, 제안 뒤 사람이 고친 내용을 덮어쓰는 문제를 막는다.
24. 결정S8 [가정] 수정은 본문을 통째로 바꾸고, publish 직전에 페이지 해시를 다시 확인한다. vault-graph는 본문을 합치지 않는다(결정7).
25. 결정S9 [가정] MCP 검색 도구에 `cwd`가 없으면 MCP 서버 프로세스의 작업 디렉터리를 쓴다. 대안은 9절 질문2. 2026-11-02 의도 검수 반영(F4, F7): 같은 규칙을 쓰기 도구 세 개와 `find_related`, `get_decision_trace`, `summarize_project_memory`, `get_open_questions`, `get_recent_changes`에도 쓴다(V2, V3).
26. 결정S10 [가정] `vg hook capture`는 수집 직후 색인하지 않는다. 이유: 수집 훅은 60초 안에 끝나야 하고, 색인은 임베딩 모델을 연다. 대안은 9절 질문4. 2026-11-02 의도 검수 반영(F1): 수집 훅은 그대로 색인하지 않는다. 다만 "새 파일은 `vg watch`나 다음 `vg index`가 색인한다"는 부분은 바꾼다. 저장한 기억이 `vg index` 전까지 회상·검색에 없어 §0 규칙4에 어긋났기 때문이다. 이제 `vg hook session-start`가 회상 전에 연결 Vault의 바뀐 파일을 임베딩 없이 메타데이터·그래프로 색인하고(기본 5초), MCP 쓰기 도구는 `published` 뒤 그 Vault를 백그라운드로 증분 색인한다(V5). 2026-11-02 재검수 반영(발견1·3): 세션 시작 갱신은 시간 한도 안에서만 바뀐 파일을 찾고, 바뀐 파일이 200개를 넘거나 발행 잠금을 1초 안에 얻지 못하면 건너뛴다. 회상 출력 뒤에는 바뀐 파일이 있는 Vault마다 분리된 프로세스로 `vg index`를 실행해 벡터를 채운다. 그래서 세션 시작 갱신 뒤에도 의미 검색이 꺼진 채로 남지 않는다(V5). 2026-11-02 3차 검수 반영(발견8·10): 세션 시작 갱신은 바뀐 파일만 읽고, 색인된 문서가 1,500개를 넘거나 지난 갱신 시간으로 보아 5초 안에 끝나지 않으면 건너뛴다. 이런 Vault에서 MCP 밖에서 바뀐 파일은 그다음 세션 회상부터 나온다. 백그라운드 `vg index`는 회상 출력 뒤가 아니라 바뀐 파일 찾기 직후에 띄우고, 훅의 갱신이 끝난 뒤 시작한다. 벡터가 오래된 연결 Vault도 다시 색인하므로, 죽은 백그라운드 색인은 다음 세션 시작에서 다시 실행된다(V5).
27. 결정S11 [가정] 구획A 항목은 제목 줄과 `summary` 줄 두 줄이고, 예산은 400토큰이다(이전 spec 4.2.3의 목표값 유지).
28. 결정S12 [가정] vault-builder에 `set-role`, `set-default-write` 명령을 더한다. 이유: 소유자가 팀 Vault를 더하는 길이 지금 손 편집뿐이다(발견12). 대안은 9절 질문8.
29. 결정S13 [가정] 훅 실행기는 `VAULT_GRAPH_BIN`, install 때 기록한 경로, `PATH` 순으로 vg를 찾는다. 이유: 훅은 사용자 셸의 가상환경 `PATH`를 물려받지 않을 수 있다. 대안은 9절 질문9.
30. 결정S14 [가정] `retired` 페이지는 기본 검색 결과에서 뺀다. 대안은 9절 질문3.

## 6. Failure and boundary behavior

| 상황 | 소유 | 동작 |
|---|---|---|
| 쓰기에서 `vault`도 기본 저장 Vault도 없고 연결 Vault가 둘 이상 | vault-graph | `vault_required`와 후보 `{name, role}` 목록을 돌려준다. Vault 명령을 부르지 않는다. |
| `vault`가 프로젝트에 연결되지 않은 Vault 이름 | vault-graph | `rejected`, "이 프로젝트에 연결된 Vault가 아니다"와 연결 Vault 목록을 돌려준다. |
| `default_write_vault`가 프로젝트 `vaults`에 없거나 문자열이 아님 | vault-graph | 그 필드만 무시하고 경고를 낸다. `vg status`에 보인다. 선택은 결정12의 3단계로 넘어간다. |
| `cwd`가 프로젝트로 풀리지 않음(검색) | vault-graph | 활성 Vault 하나를 검색한다(지금과 같음). |
| `cwd` 프로젝트의 Vault가 Graph Home에 하나도 등록되지 않음(검색) | vault-graph | 활성 Vault로 돌아가지 않는다. 빈 결과와 경고 "프로젝트 Vault가 등록되지 않음, `vg setup` 필요"를 돌려준다. 다른 Vault 결과를 섞지 않기 위해서다. |
| 연결 Vault 일부만 색인됨 | vault-graph | 색인된 Vault만 검색하고 빠진 Vault 이름을 경고에 적는다. |
| 결과의 Vault가 `vault-map.json`에 없음 | vault-graph | `vault_name`, `vault_role`이 `null`이다. |
| 같은 경로의 페이지가 이미 있음(추가) | vault-graph | publish 전에 `rejected`, "`update_memory`를 쓰라"는 메시지. |
| 수정·폐기 대상이 없음 | vault-graph | `rejected`. Vault 명령을 부르지 않는다. |
| 수정 중 읽은 뒤 페이지가 바뀜 | vault-graph | `rejected`, "다시 읽고 시도하라". |
| 페이지나 절이 사람에게 잠김 | vault-builder가 거부, vault-graph가 전달 | 계약1 `reason: human-locked`, vault-graph는 `rejected`와 Vault 메시지를 그대로 돌려준다. |
| Vault lint가 쓰기 전부터 깨져 있음 | vault-builder | 계약1 `reason: lint-dirty-before`, 종료 코드 1. vault-graph는 `rejected`와 "Vault lint를 먼저 고쳐라"를 돌려준다. |
| 적용 뒤 lint 실패 | vault-builder | 원래 파일로 되돌리고 `reason: lint-failed-after`. |
| `retired`인데 `retired_reason`이 빔 | vault-graph가 먼저, vault-builder lint가 다시 | vault-graph는 입력 확인에서 `rejected`. Vault lint도 오류로 막는다. |
| `replaced_by` 페이지가 같은 Vault에 없음 | vault-graph | `rejected`. 다른 Vault 페이지로 대체를 걸지 않는다(Vault 링크 규칙이 한 Vault 안이다). |
| Vault 도구가 계약 4 미만(`--json`을 모름) | vault-graph | 종료 코드 2와 `unrecognized arguments`를 보고 `error`, "Vault를 계약 4로 마이그레이션하라". |
| Vault 명령 표준 출력이 JSON이 아님 | vault-graph | `error`와 표준 출력·오류 마지막 20줄. |
| Vault 명령 시간 초과(120초) | vault-graph | `error`, "결과를 모른다, Vault git status를 확인하라"(지금과 같음). |
| `review propose`의 draft 검증 실패 | vault-builder | 아무 파일도 쓰지 않고 종료 코드 1. vault-graph는 `rejected`. |
| 승인 때 대상 페이지가 제안 뒤 바뀜 | vault-builder | `review resolve` 종료 코드 1, 항목은 `pending`. 사람이 거부하고 다시 제안해야 한다. |
| 승인 때 발행이 거부됨(lint 등) | vault-builder | 항목은 `pending`, 종료 코드 1, 계약1 `reason`을 출력. |
| 거부(`--status rejected`) | vault-builder | 상태만 바꾸고 draft 사본은 남긴다. wiki는 바뀌지 않는다. |
| 고정 기억이 400토큰을 넘음 | vault-graph | 뒤에서부터 줄이고 "N개 생략". 구획B 예산을 침범하지 않는다. |
| `pin`이 문자열 `"true"` 등 불리언이 아님 | 두 저장소 | Vault lint가 오류로 막는다. 이미 들어 있으면 vault-graph는 불리언 `true`만 고정으로 보고, 그 페이지를 구획B에 넣는다. |
| 모르는 `memory_schema` 값 | vault-graph | 회상에서 그 페이지를 지금처럼 일반 페이지로 다루고 표준 오류에 경고 한 줄(이전 spec n차-2의 방향). |
| 사용 기록 파일이 없거나 읽기 실패 | vault-graph | 구획A·B는 같다. 구획C는 14일 대체 규칙으로 돌아간다(지금과 같음). |
| 훅 실행기에서 vg를 찾지 못함 | vault-builder | 직접 수집(`capture --direct`) 또는 `recall.sh`. 종료 코드 0. |
| `vg hook capture` 실패 또는 시간 초과 | vault-graph 종료 코드 3, vault-builder 실행기가 직접 수집 | 같은 세션을 두 번 수집해도 새 턴만 덧붙는다. |
| 프로젝트에 role `project` Vault가 없거나 둘 이상(수집) | vault-builder | 지금 `sessions capture` 동작 그대로 건너뛰고 이유를 표준 오류에 적는다. 훅은 0으로 끝난다. |
| Vault 계약 3 미만(수집) | vault-builder | 지금처럼 건너뛰고 마이그레이션을 안내한다. |
| `settings.json`에 다른 프로그램의 훅이 있음 | vault-builder | 보존하고 자기 항목만 더한다. `settings.json`이 JSON이 아니면 install을 멈추고 아무것도 쓰지 않는다. |
| Graph Home을 지움 | vault-graph | 기억은 그대로다. `vg setup`, `vg index` 뒤 회상 구획A·B와 검색 결과가 지우기 전과 같다. |
| 프로젝트에 Vault가 하나뿐 | vault-graph | 결정12의 3단계로 그 Vault에 쓴다. 검색 결과 표시는 같은 방식으로 붙는다. |

## 7. What could be wrong

이 절은 확인하지 못한 사실이다. 각 줄의 "확인 방법"을 해당 단계 시작 때 먼저 한다.

| 코드 | 확인하지 못한 사실 | 틀리면 | 확인 방법 |
|---|---|---|---|
| 위험1 | Claude Code의 PreCompact·SessionEnd 훅 입력에 `transcript_path`, `cwd`, `session_id`, `hook_event_name`이 들어 있다. | 수집이 `Hook JSON has no transcript_path`로 건너뛴다(`session_capture.py:404-406`). | B5 시작 때 Claude Code 훅 문서와 실제 훅 입력을 파일로 떠서 본다. |
| 위험2 | 훅 항목의 `timeout`을 Claude Code가 받고, SessionEnd 훅이 세션 종료를 기다려 준다. | 긴 세션의 수집이 중간에 끊긴다. 다음 PreCompact나 수동 `sessions capture`가 남은 턴을 덧붙인다. | G9 수동 확인에서 긴 세션을 끝내고 part 파일 수를 본다. |
| 위험3 | Claude Code 훅은 사용자 셸의 `PATH`를 그대로 받지 않을 수 있다. | 실행기가 vg를 못 찾아 늘 직접 수집과 `recall.sh`로 간다. 기능은 되지만 vg 회상이 안 들어간다. | 결정S13의 기록 경로로 막는다. G9에서 회상 출력에 구획 제목 `## 고정 기억`이 있는지 본다. |
| 위험4 | `retired`를 더해도 다른 Vault 도구(검색, 지도, 지표, `memory_scan`, router의 status 처리)가 깨지지 않는다. status 목록을 쓰는 곳을 모두 찾지 않았다. | release gate의 health·maps·metrics 검사가 실패하거나, 폐기 페이지가 Vault 검색에 현재 페이지로 나온다. | B2에서 `tools/`와 router asset 전체를 `deprecated`로 검색해 같은 자리에 `retired`를 더한다. |
| 위험5 | vault-graph 메타데이터 저장소의 문서 frontmatter가 M05 검색 단계에서 읽기 포트로 닿는다. | 결정S14(`retired` 제외)를 M05 안에서 할 수 없고, 구성 지점에서 걸러야 한다. 결과 수가 `limit`보다 적어질 수 있다. | G3 시작 때 `retrieval/search/`의 문서 읽기 포트를 확인한다. |
| 위험6 | vault-graph의 frontmatter 파서가 YAML 불리언 `true`를 파이썬 `True`로 준다. | 구획A가 비어 있다. | G5에서 `DocumentSnapshot.frontmatter`의 `pin` 값 형식을 테스트로 고정한다. |
| 위험7 | 실행기 `capture --direct`의 Vault 선택이 `session_capture.py:431-479`와 같은 규칙을 다시 구현한다. 두 곳이 어긋날 수 있다. | 실행기가 고른 Vault의 도구가 다른 Vault에 쓰거나 건너뛴다. | B5에서 실행기가 같은 규칙 함수를 가져다 쓸 수 있는지 본다. 못 하면 두 구현을 같은 표 테스트로 묶는다. |
| 위험8 | 계약 4 마이그레이션이 기존 Vault의 `tools/wiki`를 사람이 고친 경우 덮어쓰지 않고 멈춘다. | 사람이 고친 Vault 도구가 바뀐다. | B6에서 기존 마이그레이션의 `managed_paths.py` 규칙을 확인한다. |
| 위험9 | 프로세스 안 잠금(`_vault_lock`)만으로 충분하다. MCP 서버가 여러 개(세션마다 하나) 떠서 같은 Vault에 쓰면 잠금이 공유되지 않는다. | 두 세션이 같은 페이지를 동시에 수정하면 늦게 끝난 쪽이 이긴다. 수정의 해시 재확인이 대부분 막지만 완전하지 않다. | 이번에는 받아들이고 기록한다. 필요하면 Vault 쪽 파일 잠금을 다음 요청으로 보낸다. |
| 위험10 | MCP 서버 프로세스의 작업 디렉터리가 Claude Code 세션의 프로젝트 폴더다. | `cwd` 없는 MCP 검색이 활성 Vault로 돌아간다(지금 동작과 같음). | G3에서 MCP 서버 시작 위치를 실제 세션으로 확인한다. 에이전트 지침에 `cwd`를 넘기라고 적는다. |
| 위험11 | E2E 테스트가 vault-builder 템플릿으로 임시 Vault를 만들 수 있다. 위치는 환경 변수 `VAULT_BUILDER_ROOT`로 받는다. [가정] | 변수가 없으면 E2E가 건너뛴다. 이 경우 A-1~A-6을 증명하지 못한다. | G8 완료 증거에 변수를 설정한 실행 로그를 붙인다. |
| 위험12 | 검색 결과 JSON에 필드를 더하고 MCP 도구를 두 개 늘리는 것은 `docs/SPEC.md` §5 "이름과 입력·출력 스키마를 바꾸지 않는다"의 예외다. 더하기만 하므로 기존 호출은 깨지지 않는다고 판단했다. | 출력 스키마를 엄격히 비교하는 소비자가 실패한다. | 단계0에서 §5를 "기존 필드는 바꾸지 않고, 선택 필드와 도구를 더할 수 있다"로 고친다. 사용자 확인은 9절 질문1. |

## 8. Acceptance criteria

### 8.1 사용자 성공 시나리오 (brief 6번)

A-1~A-6은 vault-graph `tests/e2e/test_long_term_memory_scenarios.py` 하나에 시나리오별 테스트로 둔다.

- 각 테스트는 환경 변수 `VAULT_BUILDER_ROOT`의 vault-builder로 임시 HOME 아래에 Vault를 만든다.
- 임시 `vault-map.json`과 임시 Graph Home을 쓴다.
- 실제 Vault 도구를 하위 프로세스로 부른다. 가짜 포트를 쓰지 않는다.
- 완료 증거는 변수를 설정하고 실행한 로그다(위험11).

- A-1 (시나리오① 고정 기억이 먼저)
  - 준비: 프로젝트에 Vault 둘(role `project`, `team`)을 연결한다. `team` Vault에 `pin: true` 페이지 하나, `project` Vault에 더 최근 날짜의 일반 페이지 여러 개를 둔다.
  - 기대: `vg hook session-start`(source `startup`)의 출력이 다음을 모두 만족한다.
    - 첫 구획 제목이 `## 고정 기억`이고, 고정 페이지가 그 안에 있다.
    - 고정 페이지는 `## 기억 목록`에 다시 나오지 않는다.
    - 출력은 1,500토큰과 9,000자 이하다. 구획A는 400토큰 이하다.
- A-2 (시나리오② stated 추가·수정·폐기)
  - 추가: `remember(basis="stated", pin=True, memory_kind="rule")`가 `published`를 돌려준다. 페이지 frontmatter에 `memory_schema: vault-memory/v1`, `pin: true`, `memory_kind: rule`이 있다.
  - 수정: 같은 경로에 `update_memory`를 하면 본문이 새 내용이고 `updated`가 오늘이다.
  - 폐기: `retire_memory(reason=...)`를 하면 다음이 모두 참이다.
    - 파일이 남아 있다.
    - status가 `retired`이고 `retired_reason`, `retired_at`이 채워져 있다.
    - `vg index` 뒤 회상 구획A·B와 기본 `vg search`에 그 페이지가 없다.
    - 구획C에 "폐기됨: <사유>" 줄이 한 번 나온다.
  - 대체 폐기: `retire_memory(replaced_by=...)`를 하면 `status: deprecated`와 `superseded_by`가 생긴다.
  - 잠긴 페이지: 사람이 잠근 페이지에 `update_memory`를 하면 `rejected`이고, 메시지에 Vault의 잠금 거부 문구가 있다.
- A-3 (시나리오③ inferred 대기와 승인)
  - 제안: `remember(basis="inferred")`가 `proposed`와 `scratch/review/` 아래 `review_path`를 돌려준다. `wiki/` 아래 파일 바이트가 호출 전과 같다.
  - 승인 전: `vg index` 뒤 `vg search`와 회상 어디에도 제안 내용이 없다.
  - 승인: 사람 명령 `review resolve <review_path> --status accepted --resolution ...`이 종료 코드 0으로 끝나고 페이지가 `wiki/`에 생긴다. `vg index` 뒤 검색에 나온다.
  - 거부: 다른 제안을 `--status rejected`로 끝내면 기억 페이지가 만들어지거나 바뀌지 않는다. `wiki/log.md`에는 기존 resolve처럼 "Review rejected" 기록 한 줄이 더해진다(2026-11-02 사용자 결정).
- A-4 (시나리오④ 세션 종료 때 원문 저장)
  - 준비: 대화 JSONL 고정 파일과 SessionEnd 훅 JSON을 만든다.
  - vg 경로: `vault_hooks.py capture`가 `vg hook capture`를 거쳐 project Vault `raw/sessions/` 아래에 새 파일을 만든다.
  - 직접 경로: `VAULT_GRAPH_BIN`을 없는 경로로 두고 같은 일을 하면 직접 수집으로 같은 결과가 나온다.
  - 반복: 같은 세션을 다시 보내면 새 파일이 생기지 않는다(새 턴이 없을 때).
  - PreCompact 훅 JSON도 같은 결과다.
  - 종료 코드: 실행기는 모든 경우에 0으로 끝난다.
- A-5 (시나리오⑤ 검색 결과에 Vault 이름·종류)
  - 준비: 프로젝트에 Vault 셋(role `personal`, `project`, `team`)을 연결하고 모두 등록·색인한다.
  - CLI: 프로젝트 폴더에서 범위 없이 `vg search --format json`을 하면 결과가 둘 이상의 Vault에서 한 목록으로 나온다. 결과마다 `vault_name`, `vault_role`이 `vault-map.json` 값과 같다.
  - MCP: `search_vault(cwd=<프로젝트 폴더>)`도 같다.
  - 프로젝트 밖: 프로젝트 밖 폴더에서 범위 없이 검색하면 활성 Vault 결과만 나온다.
- A-6 (시나리오⑥ Graph Home을 지워도 손실 없음)
  - 기록: 회상 출력(구획A·B), 질문 3개의 `vg search` 상위 5개 결과(Vault 이름, 경로), 모든 Vault 파일의 sha256 목록을 저장한다.
  - 다시 만들기: Graph Home 폴더를 지우고 `vg setup`, `vg index`를 한다.
  - 기대: 회상 구획A·B가 바이트 단위로 같다. 검색 상위 5개가 같다. Vault 파일 sha256 목록이 처음과 같다.
- A-7 (수동 확인 1회, 실제 세션)
  - 준비: 사용자 컴퓨터에서 `install --with-hooks`를 실행한다.
  - 실제 Claude Code 세션 하나에서 다음 다섯 가지를 확인한다.
    1. 세션 시작 문맥에 `## 고정 기억`이 있다.
    2. 에이전트에게 사실 하나를 기억하라고 말하면 Vault에 페이지가 생긴다.
    3. 추론 사실 하나가 `scratch/review/`에 대기한다.
    4. 세션을 끝내면 `raw/sessions/`에 원문 파일이 생긴다.
    5. 검색 결과에 Vault 이름·종류가 붙는다.
  - 결과 요약(비밀값 없이)을 vault-graph PR 설명에 적는다.

### 8.2 기능별 기준

- A-8 결정12 저장 Vault 고르기
  - 단위 테스트 표:
    - Vault 둘 + 기본 없음 + `vault` 없음 → `vault_required`와 후보 둘.
    - 기본 있음 → 기본 Vault.
    - `vault`가 프로젝트에 연결되지 않은 이름 → `rejected`.
    - 연결 Vault 하나 → 그 Vault.
  - `memory_kind`를 바꿔도 고른 Vault가 같다.
- A-9 사용 기록과 순위
  - 같은 문서 집합에 사용 기록 네 가지를 넣는다: 없음, 10회 주입 0회 열람, 내용 해시 변경, `usage/` 읽기 실패.
  - 네 경우 모두 구획A·B 텍스트가 같다.
  - `DEMOTE_AFTER_INJECTIONS`가 코드에 없다.
- A-10 결정S14
  - `retired` 페이지는 기본 검색 결과에 없다.
  - 같은 질의에서 `deprecated` 페이지는 지금처럼 나온다.
  - `docs/DECISIONS.md`에 INV-05 예외 항목이 있다.
- A-11 계약1(vault-builder)
  - `publish-draft --json`이 `reason` 일곱 가지 각각에서 정해진 필드와 종료 코드(0/1)를 낸다. 일곱 가지는 null, `lint-dirty-before`, `draft-invalid`, `human-locked`, `page-missing`, `lint-failed-after`, `io-error`다.
  - 표준 출력은 `json.loads`로 읽힌다.
  - `--json` 없는 기존 publish-draft 테스트가 그대로 통과한다.
- A-12 계약2(vault-builder)
  - lint가 네 경우에 오류를 낸다: `pin: "yes"`, 허용 밖 `memory_kind`, `memory_schema` 없는 `pin`, `retired_reason` 없는 `retired`.
  - 새 필드가 없는 기존 페이지로 만든 Vault의 lint는 그대로 통과한다.
- A-13 계약3(vault-builder)
  - frontmatter만 있는 `patch-page`는 적용된다.
  - `edits`와 `frontmatter`가 모두 비면 거부된다.
- A-14 계약4(vault-builder)
  - 요약만 다른 한국어 제안 두 개가 서로 다른 `review_id`를 받는다.
  - 다음 경우를 각각 테스트한다: `propose` 검증 실패 시 파일 0개, 승인 성공, 대상 해시가 달라 승인 거부, 발행 거부 시 `pending` 유지, `rejected` 시 기억 페이지 무변경(`wiki/log.md` 기록 한 줄만 더해짐).
  - 다른 검토 유형의 기존 테스트가 그대로 통과한다.
- A-15 계약5(vault-builder)
  - `set-role`과 `set-default-write`가 다른 필드를 보존한다.
  - install·link 뒤 `default_write_vault`가 남는다.
  - 기본 저장 Vault를 unlink하면 필드가 지워진다.
  - router 테스트(`builder_tests.test_llm_wiki_router`)가 새 필드가 있는 map으로 통과한다.
  - `docs/contracts/vault-map-v2.md`가 있다.
- A-16 계약6(vault-builder)
  - `install --with-hooks`가 세 훅 항목을 더한다.
  - 두 번째 실행은 `settings.json` 바이트를 바꾸지 않는다.
  - 미리 넣어 둔 다른 훅 항목이 남는다.
  - uninstall 뒤 자기 항목만 사라진다.
  - `--with-hooks` 없는 install은 `settings.json` 바이트를 바꾸지 않는다.
  - 실행기는 vg 없음, vg 실패, vg 시간 초과에서 모두 종료 코드 0이다.
- A-17 계약7(vault-builder)
  - `MANIFEST_CONTRACT_VERSION`이 4다.
  - 계약 3 고정 Vault를 audit → apply 하면 계약 4가 되고 lint가 통과한다.
  - vault-graph가 계약 3 Vault에 `remember`를 하면 `error`와 마이그레이션 안내를 돌려준다.
- A-18 Vault 직접 쓰기 없음(vault-graph)
  - 기존 read-only 경계 테스트가 통과한다.
  - 가짜 `VaultWriter`로 `remember`, `update_memory`, `retire_memory`, `vg hook capture`를 실행해도 Vault 폴더의 파일 sha256이 바뀌지 않는다.
  - `src/vault_graph/operation/memory/`에 파일 쓰기 호출(`write_text`, `write_bytes`, 쓰기 모드 `open`)은 운영체제 임시 디렉터리 draft 하나뿐이다.

### 8.3 모듈화 (사용자 추가 요구)

- A-19 vault-graph 방향 검사
  - `tests/test_feature_import_direction.py`가 통과한다. `_KNOWN_VIOLATIONS == frozenset()`이고 `_KNOWN_VIOLATION_CEILING == 0`이다.
  - `_AREAS`에 `operation/memory/`가 M18로 있다.
  - `_ALLOWED`에서 어떤 영역도 M18을 가리키지 않는다.
- A-20 vault-graph 순환·기능 경계
  - `tests/test_module_import_cycles.py`가 0건으로 통과한다. `tests/test_functional_module_boundaries.py`도 통과한다.
  - `vault_graph.operation.integration.remember_service`를 가져오는 파일이 없다.
- A-21 vault-builder 방향 검사
  - `tests/test_wiki_lib_import_direction.py`가 4.4의 방향을 검사하고 통과한다.
  - `review.py`는 `memory_proposal`을, `publish.py`는 `review`와 `memory_proposal`을, `hooks.py`와 `map_settings.py`는 서로를 가져오지 않는다.

### 8.4 범위·호환·작업 조건 (사용자가 준 제한)

- A-22 호환
  - `default_write_vault`가 없는 version 2 map에서 기존 vault-graph 테스트와 router 테스트가 그대로 통과한다.
  - 기존 MCP 도구 11개와 CLI 명령의 기존 입력·출력 필드가 그대로다. 기존 계약 테스트가 통과한다.
  - 명시적 `scope`를 준 검색 결과는 `vault_name`·`vault_role` 필드 추가 외에 변경 전과 같다.
- A-23 브랜치와 순서
  - vault-graph 커밋은 모두 `feat/jh/local-graph`에, vault-builder 커밋은 모두 `feat/jh/vault-graph-requests`에 있다.
  - 이 작업의 첫 vault-graph 커밋은 단계0(SPEC §0 결정12~15, DECISIONS 2026-11-02, 이 spec)이다.
  - 계약을 쓰는 G 단계 커밋은 그 계약의 B 단계 커밋보다 시간상 뒤다.
- A-24 전체 검사
  - vault-graph `pytest` 전체가 통과한다.
  - vault-builder `bash scripts/release_gate.sh`(`WIKI_GATE_FULL=1`)와 `python3 -m unittest builder_tests.test_llm_wiki_router`가 통과한다.

### 8.5 문서 갱신

- A-25 vault-graph 문서(G8 커밋까지)
  - `docs/html/2026-10-29-vault-memory-design.html`
    - "여러 Vault 연결은 vault-builder 몫", "검색·회상 계층", "remember 단일 쓰기" 문장이 없다.
    - 여러 Vault 검색·표시, 추가·수정·폐기·제안, 수집 시점, 고정 회상 흐름이 있다.
  - `docs/SPEC.md`
    - §0 "현재 구현과의 차이"가 남은 일만 적는다.
    - §2 표와 §3의 "쓰기, 검증, 여러 Vault 연결은 vault-graph 몫이 아님"(87행)을 고친다.
    - §4 쓰는 대상에 publish-draft, `review propose`, 수집 실행기 세 경로를 적고, 사용 기록이 순위에 영향을 주지 않는다고 적는다.
    - §5에 MCP 14개, `vg hook capture`, "선택 필드·도구 추가는 허용" 규칙을 적는다.
    - §6에 `default_write_vault`와 계약1 JSON을 적는다.
    - §9.3 의존 상태를 구현됨으로 바꾼다.
  - `docs/ARCHITECTURE.md` §4: M18과 새 파일 위치.
  - VG-MOD
    - §3 표에 M18 행이 있다.
    - INV-01에 Vault 쓰기 경로 목록이 있다.
    - INV-02의 "구획B 순서만 기본으로 돌아간다"를 "구획A·B는 같다, 구획C 알림이 다시 나올 수 있다"로 고친다.
    - INV-05 예외(`retired` 제외)가 있다.
  - `README.md` 5-17행: 장기 기억 도구 설명과 쓰기 도구 세 개.
  - `AGENTS.md` Project Boundary: "The only path that writes to Vault is `remember`"를 새 쓰기 경로로 고친다. 사용자 목록에는 없지만 저장소 규칙 문서가 구현과 어긋나지 않게 하기 위해서다. [가정]
- A-26 vault-builder 문서(B7 커밋까지)
  - `docs/html/project-memory-structure.html`
    - SessionStart 훅의 "새로" 표시가 `--with-hooks` 선택 항목 설명으로 바뀐다.
    - PreCompact·SessionEnd 수집 흐름과 추론 제안 → 승인 흐름이 있다.
  - `docs/html/vault-roadmap.html`
    - 요청3~6과 새 계약(계약3, 계약4)의 상태가 구현됨이다.
    - `retired` 상태가 있다.
    - 결정2("vault-graph는 vault-map을 읽기만 한다")는 유지된다는 점이 적혀 있다.
  - `docs/html/vault-structure-map.html`: `default_write_vault`, role 값(personal, project, team, 그 밖)과 `set-role`, `set-default-write`가 있다.
  - `docs/superpowers/specs/2026-10-29-vault-graph-requests-ko.md`: 각 요청의 상태 열이 갱신되어 있다.

## 9. Open decisions

spec gate에서 답할 질문이다. 각 질문은 이 spec을 읽지 않아도 답할 수 있게 썼다. 권장안대로 답하면 spec을 고치지 않아도 된다.

**답 (2026-11-02, 사용자):** spec 승인. 5절의 [가정]은 이 승인으로 확정한다. 질문1~9 모두 권장안으로 확정. G9 실제 세션 확인용 project Vault 위치는 `$HOME/vaults/vault-graph`다. `$HOME/.claude/settings.json` 훅 설치는 G9 직전에 한 번 더 확인을 받는다.

### 질문1 수정·폐기를 별도 MCP 도구로 둘 것인가

- 정할 것: 에이전트가 기억을 고치거나 폐기할 때 부르는 MCP 도구의 모양.
- 배경: 지금 MCP 도구는 12개이고 `remember`는 새 페이지 추가만 한다. `docs/SPEC.md` §5는 "도구 이름과 입출력 스키마를 바꾸지 않는다"고 적고 있다. 선택지는 두 가지다.
  - 옵션1: 새 도구 `update_memory`, `retire_memory`를 더한다(14개).
  - 옵션2: `remember`에 `action`(`add`, `update`, `retire`) 인자를 더한다(12개 유지).
- 권장: 옵션1. 동작마다 필수 입력이 달라서(폐기는 `reason`, 수정은 `path`) 도구 하나에 넣으면 "이 조합에서만 필수" 규칙이 생기고 에이전트가 틀리기 쉽다. 기존 11개 도구의 입출력은 바뀌지 않는다.
- 답이 바꾸는 것: 옵션2면 V3의 도구 목록, A-2·A-3의 호출 모양, SPEC §5의 도구 수가 바뀐다. 어느 쪽이든 §5에 "선택 필드와 도구를 더할 수 있다"는 규칙을 적는다(위험12).

### 질문2 MCP 검색에 `cwd`가 없을 때 서버 작업 디렉터리를 쓸 것인가

- 정할 것: 에이전트가 `search_vault`에 `cwd`를 넘기지 않았을 때 검색할 Vault.
- 배경: 결정13은 "프로젝트에 연결된 모든 Vault를 검색한다"이다. MCP 서버는 Claude Code가 띄우므로 보통 프로젝트 폴더에서 돈다. 다만 확인하지 않았다(위험10). 선택지는 두 가지다.
  - 옵션1: 서버 작업 디렉터리로 프로젝트를 찾는다.
  - 옵션2: `cwd`가 없으면 지금처럼 활성 Vault 하나만 찾는다.
- 권장: 옵션1. 에이전트가 `cwd`를 빠뜨려도 결정13대로 동작한다. 프로젝트를 찾지 못하면 지금과 같은 결과로 돌아가므로 손해가 작다.
- 답이 바꾸는 것: 옵션2면 V2의 `cwd` 규칙과 결정S9가 바뀐다. 에이전트 지침에 "`cwd`를 반드시 넘겨라"를 넣어야 한다.

### 질문3 폐기(`retired`) 페이지를 기본 검색 결과에서 뺄 것인가

- 정할 것: 폐기한 기억이 작업 중 검색에 나오는지.
- 배경: 회상은 폐기 페이지를 넣지 않는다. 검색은 지금 페이지 status로 결과를 거르지 않는다. 대체된(`deprecated`) 페이지도 나온다. 폐기 페이지가 나오면 에이전트는 그 내용이 더는 맞지 않는다는 것을 모른다. 결과에서 빼면 VG-MOD INV-05(검색 점수·순서 유지)의 예외가 된다. 선택지는 세 가지다.
  - 옵션1: `retired`만 뺀다.
  - 옵션2: `retired`와 `deprecated`를 모두 뺀다.
  - 옵션3: 빼지 않는다.
- 권장: 옵션1. 폐기는 "대체도 없이 더는 맞지 않음"이라 보여 줄 이유가 없다. `deprecated`는 대체 페이지를 찾는 단서라 지금처럼 둔다. 그 처리는 이전 spec의 n차-1에서 다룬다.
- 답이 바꾸는 것: 옵션2면 A-10과 n차-1 범위가 바뀐다. 옵션3이면 결정S14와 A-2의 검색 조건, A-10이 빠진다.

### 질문4 세션 원문을 수집한 직후 vault-graph가 색인할 것인가

- 정할 것: 세션 종료 훅 안에서 `vg index`까지 할지.
- 배경: 수집된 원문은 색인되어야 검색에 나온다. 색인은 임베딩 모델을 열어 수 초 이상 걸릴 수 있다. 수집 훅의 시간 제한은 60초로 잡았다. 선택지는 세 가지다.
  - 옵션1: 훅에서는 수집만 하고, 색인은 `vg watch`나 다음 `vg index`가 한다.
  - 옵션2: 수집 뒤 색인을 백그라운드 프로세스로 띄운다.
  - 옵션3: 훅 안에서 색인까지 끝낸다.
- 권장: 옵션1. 훅이 짧고 실패 지점이 적다. 옵션2는 세션이 끝난 뒤 남는 프로세스를 관리해야 한다.
- 답이 바꾸는 것: 옵션2나 옵션3이면 V5에 색인 단계가 생긴다. Graph Home 쓰기가 생기므로 INV-02 문구와 A-4 기대 결과도 바뀐다.
- 2026-11-02 의도 검수 반영(F1): 옵션1은 유지한다. 수집 훅은 색인하지 않으므로 A-4는 그대로다. 대신 세션 시작 훅과 MCP 발행 뒤 색인이 Graph Home에 새 세대를 쓴다. 그래서 VG-MOD INV-02에 "`vg hook session-start`의 회상 전 색인 갱신" 예외를 더했다(결정S10, V5).

### 질문5 폐기를 어떤 Vault draft로 보낼 것인가

- 정할 것: vault-graph가 폐기를 Vault에 전하는 형식.
- 배경: 폐기는 frontmatter의 status와 사유만 바꾼다. 지금 Vault의 `patch-page`는 본문 편집(`edits`)이 하나 이상 있어야 한다. 선택지는 두 가지다.
  - 옵션1: Vault가 frontmatter만 있는 `patch-page`를 받게 한다(계약3, vault-builder 작은 변경).
  - 옵션2: vault-graph가 현재 페이지 전체를 읽어 status만 바꾼 `upsert-page`로 보낸다(Vault 변경 없음).
- 권장: 옵션1. Vault가 적용하는 순간의 파일을 쓰므로, 읽은 뒤 사람이 고친 본문을 vault-graph가 옛 본문으로 덮어쓸 위험이 없다.
- 답이 바꾸는 것: 옵션2면 계약3과 B2 일부, A-13이 빠진다. 폐기에도 수정과 같은 해시 재확인을 넣어야 한다.

### 질문6 쓰기 도구의 `basis`를 필수로 할 것인가

- 정할 것: 에이전트가 사실의 출처(`stated` = 사용자가 말함, `inferred` = 에이전트가 추론함)를 꼭 밝혀야 하는지.
- 배경: `stated`는 바로 확정되고, `inferred`는 사람 승인을 기다린다. 선택지는 두 가지다.
  - 옵션1: 필수, 기본값 없음.
  - 옵션2: 기본값 `stated`.
- 권장: 옵션1. 기본값이 `stated`면 에이전트가 추론한 사실이 검토 없이 확정될 수 있다. 이것은 §0 규칙2에 어긋난다.
- 답이 바꾸는 것: 옵션2면 V3 시그니처와 결정S5가 바뀐다. 7절에 "`basis`를 빠뜨린 추론이 검토 없이 확정될 수 있다"는 위험을 더한다.

### 질문7 Vault 기억 쓰기를 새 모듈 영역(M18)으로 분리할 것인가

- 정할 것: vault-graph 코드에서 기억 추가·수정·폐기·제안 코드를 둘 자리.
- 배경: 지금 `remember` 코드는 설정 기록 영역 M17(`operation/integration/`)에 있다. 모듈 설계 문서는 M17의 책임을 "명시적 설정 기록"으로 정하고 "Vault 내용 수정"을 경계 밖으로 둔다. 선택지는 두 가지다.
  - 옵션1: 새 영역 M18 `operation/memory/`를 만들고 옮긴다. 허용 방향은 M01, M12다.
  - 옵션2: M17에 그대로 두고 파일만 더한다.
- 권장: 옵션1. 바뀌는 이유가 다른 코드(설정 설치 대 기억 쓰기)를 나누는 것이 사용자가 요구한 모듈화다. 방향 표에 영역 하나만 더하면 되고 예외는 생기지 않는다.
- 답이 바꾸는 것: 옵션2면 V1 표, G1 단계, A-19·A-20의 M18 조건이 빠진다. VG-MOD M17 정의를 "Vault 기억 쓰기 포함"으로 고쳐야 한다.

### 질문8 vault-builder에 Vault 종류와 기본 저장 Vault를 바꾸는 명령을 더할 것인가

- 정할 것: 소유자가 팀 Vault를 더하거나 기본 저장 Vault를 정하는 방법.
- 배경: 지금 install은 모든 Vault를 `personal`로 넣고, 종류를 바꾸는 명령이 없다. 기본 저장 Vault 필드는 이번에 새로 생긴다. 선택지는 두 가지다.
  - 옵션1: `set-role`, `set-default-write` 두 명령을 더한다.
  - 옵션2: 문서에 `vault-map.json` 손 편집 방법만 적는다.
- 권장: 옵션1. 손 편집은 JSON을 깨뜨리기 쉽다. 깨지면 vault-graph와 router가 map 전체를 쓰지 않는다.
- 답이 바꾸는 것: 옵션2면 계약5의 명령 두 개, `map_settings.py`, A-15 일부가 빠지고 문서 절차가 생긴다.

### 질문9 훅 실행기가 vg를 어떻게 찾을 것인가

- 정할 것: Claude Code 훅이 vault-graph 실행 파일 `vg`를 찾는 순서.
- 배경: vg는 보통 가상환경에 설치된다. Claude Code 훅은 사용자 셸의 `PATH`를 그대로 받지 않을 수 있다(위험3). 못 찾으면 훅은 Vault 도구만 쓰므로 기능은 되지만 vg 회상이 들어가지 않는다. 선택지는 두 가지다.
  - 옵션1: 환경 변수 `VAULT_GRAPH_BIN`, install 때 기록한 절대 경로, `PATH` 순서.
  - 옵션2: `PATH`만 본다.
- 권장: 옵션1. install 때 한 번 기록하면 셸 설정과 상관없이 찾는다. vg를 옮기면 환경 변수로 덮어쓸 수 있다.
- 답이 바꾸는 것: 옵션2면 `vault-hooks.json` 기록과 결정S13이 빠진다. A-7 수동 확인에서 vg 경로 문제가 나올 가능성이 커진다.
