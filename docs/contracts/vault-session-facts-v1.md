# `vault-session-facts/v1` 세션 사실 첨부 계약

근거: `docs/specs/2026-11-16-longmemeval-session-memory/spec.md` D17, D21, D25~D28, F8, F9, F12.
쓰는 쪽: vault-builder Vault 도구 `tools/wiki/cli.py sessions attach-facts`(vault-builder 저장소).
읽는 쪽: vault-graph 색인(사실 키, spec D21·D28).

vault-graph는 이 파일을 직접 쓰지 않는다. vault-graph 사실 작업자가 아래 입력 JSON을 만들어 Vault 명령에 넘기고, Vault 명령이 검증한 뒤 파일을 쓴다.

## 1. 명령

```text
python3 <vault>/tools/wiki/cli.py sessions attach-facts --session <part 경로> --facts <입력 JSON 경로> --json
```

- `--session`: 세션 part 파일 경로. Vault 루트 기준 상대 경로나 절대 경로다. `raw/sessions/` 아래 `vault-session/v2` 파일이어야 한다.
- `--facts`: 아래 §2 입력 JSON 파일 경로. Vault 밖에 있어도 된다. 명령은 이 파일을 읽기만 한다.
- 출력: 마지막 줄이 JSON 객체 하나다. `{"status": "written"|"exists"|"rejected", "path": "<첨부 Vault 상대 경로>", "reason": "<rejected일 때 이유 코드>", "facts": <쓴 사실 수>}`. `path`는 세 경우 모두 첨부가 놓일 경로다.
- 종료 코드: `written`과 `exists`는 0, `rejected`는 1, 사용법 오류는 2다.
- Vault는 명령을 실행한 `cli.py`가 들어 있는 Vault 루트다. 작업 폴더와 `vault-map.json`은 보지 않는다. `--session`이 그 루트의 `raw/sessions/` 아래가 아니면 `rejected`(`session_missing`)다. 명령이 없는 옛 Vault에서 vault-graph는 `facts_writer_missing`을 기록한다(spec F9).

## 2. 입력 JSON

```json
{
  "schema": "vault-session-facts-input/1",
  "session_id": "45d576f0-4bf0-56dd-8201-703456b8e6f4",
  "source_sha256": "<part 파일 전체 바이트의 sha256, 소문자 hex>",
  "extractor": "claude",
  "model": "claude-sonnet-5-5",
  "facts": [
    {"date": "2023-05-20", "text": "사용자는 물려받은 보석과 가구 감정을 알아보고 있다.", "exchange_id": "x0001"}
  ]
}
```

- `extractor`: `claude` 또는 `llama-server`. `model`: 추출에 쓴 모델 이름. 둘 다 빈 문자열이 아니다.
- `facts`: 0개 이상. 순서를 그대로 쓴다. 0개면 명령은 쓰지 않고 `rejected`(`no_facts`)다. vault-graph는 0개일 때 명령을 부르지 않는다(spec F8).
- `date`: `YYYY-MM-DD`. 그 사실이 일어난 날이고, 알 수 없으면 그 교환의 시작 날짜다.
- `text`: 한 줄, 앞뒤 공백 없음, 1~400자, 줄바꿈 없음. 세션의 언어를 따른다(영어로 가정하지 않는다).
- `exchange_id`: part 파일의 `<!-- vg:exchange id=<id> ... -->` 줄에 있는 id(예: `x0001`).

## 3. 첨부 파일

- 위치: part 파일과 같은 폴더, 이름은 `<part 파일 이름에서 .md를 뺀 것>.facts.md`. 예: `raw/sessions/<project>/2023-05-20-<session_id>-part1.md` → `…-part1.facts.md`.
- part 파일 하나에 첨부 하나다. 한 번 쓰면 바꾸지 않는다. 이미 있으면 `exists`이고 덮어쓰지 않는다.
- 형식:

```markdown
---
schema: vault-session-facts/v1
agent: claude-code
session_id: "45d576f0-4bf0-56dd-8201-703456b8e6f4"
part: 1
source: raw/sessions/longmemeval/2023-05-20-45d576f0-4bf0-56dd-8201-703456b8e6f4-part1.md
source_sha256: "<입력의 source_sha256>"
extractor: claude
model: claude-sonnet-5-5
generated_at: "2026-11-16T03:00:00Z"
fact_count: 1
---

- 2023-05-20 사용자는 물려받은 보석과 가구 감정을 알아보고 있다. (exchange x0001)
```

- frontmatter 키 순서는 위와 같다. `agent`, `session_id`, `part`는 part 파일 frontmatter 값을 그대로 쓴다. `source`는 Vault 루트 기준 part 경로, `generated_at`은 명령이 쓴 UTC 시각이다.
- 본문은 빈 줄 하나 뒤 사실마다 한 줄 `- <date> <text> (exchange <exchange_id>)`이고 파일은 `\n`으로 끝난다.

## 4. 검증 (명령이 쓰기 전에 확인한다)

어느 하나라도 맞지 않으면 아무 파일도 쓰지 않고 `rejected`와 이유 코드를 낸다.

| 이유 코드 | 조건 |
|---|---|
| `session_missing` | `--session` 파일이 없거나 `raw/sessions/` 아래 `vault-session/v2` 파일이 아니다 |
| `source_mismatch` | 입력 `source_sha256`이 part 파일 바이트의 sha256과 다르다 |
| `session_id_mismatch` | 입력 `session_id`가 part frontmatter `session_id`와 다르다 |
| `bad_input` | 입력 `schema`가 `vault-session-facts-input/1`이 아니거나 필수 키가 없거나 형이 다르다 |
| `no_facts` | `facts`가 비었다 |
| `unknown_exchange` | `exchange_id`가 part 파일의 `vg:exchange` id에 없다 |
| `bad_text` | `text`가 비었거나 400자를 넘거나 줄바꿈이 있다 |
| `bad_date` | `date`가 `YYYY-MM-DD` 실제 날짜가 아니다 |
| `secret` | `text`가 Vault 가림 규칙에 걸리는 값을 담는다 |

- `exists`는 검증보다 먼저 본다. 첨부가 이미 있으면 입력과 상관없이 `exists`다.
- `sessions git-check`와 `sessions capture`는 `.facts.md`를 세션 파일로 세지 않는다. `git-check`는 커밋된 `.facts.md`가 바뀌면 세션 파일과 같이 실패한다.

## 5. vault-graph가 읽는 방법

- frontmatter `schema`가 `vault-session-facts/v1`인 파일만 첨부로 본다. 세션 묶음(`session_group_key`)과 세션 교환 조각 분할에는 넣지 않는다.
- 본문 사실 줄 하나가 `derived` 조각 하나다. `parent_key`는 `<session_id>:<exchange_id>`, 시각은 줄의 `date`다. 형식에 맞지 않는 줄은 건너뛰고 색인 경고 하나를 남긴다.
- `schema`가 `vault-session-facts/`로 시작하지만 판이 다르면 색인하지 않고 경고 하나를 남긴다.
- 사실 텍스트는 검색 키로만 쓴다. 결과의 발췌, 제목, 근거 경로는 원 교환이다(spec I3).
