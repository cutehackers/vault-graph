# 층2 검색 평가 세트

spec `docs/specs/2026-11-11-search-and-memory-quality-2/spec.md` §4.1.1의 층2다. 누구나 저장소만으로 같은 점수를 다시 낼 수 있게 만든 가상 Vault와 질문 세트다.

## 내용

- `vault/`: 새로 지어낸 가상 Vault다(결정9). 실제 Vault를 옮기거나 가공하지 않았다.
  - 가상 프로젝트 셋과 개인 메모: Tidepool(React Native 모바일 앱), Ledgerline(Go 백엔드 API), gitcrumb(Rust CLI), 개인 dotfiles·홈서버.
  - `wiki/`: 76쪽. decisions 27, workflows 22, concepts 12, systems 9, sources 6. 제목은 영어, 본문은 한국어·영어 혼용, frontmatter는 `title`, `summary`, `tags`.
  - 일부러 헷갈리게 넣은 페이지: 뒤집힌 옛 결정(`superseded` tag), 같은 주제의 다른 프로젝트 결정(release-please와 git-cliff, Sentry와 OpenTelemetry 등).
  - `raw/sessions/claude-code/`: `vault-session/v1` 세션 13개. 상태 확인, 결정 논의, 코드 뜻, 위치 질문이 들어 있다.
- `questions.json`: `vg-search-eval/1` 형식(`tests/benchmarks/eval_dataset.py`), layer 2, Vault id `eval2`. 210문항.

| 종류 | 문항 | dev | test |
|---|---:|---:|---:|
| title | 30 | 15 | 15 |
| paraphrase | 36 | 18 | 18 |
| decision | 36 | 18 | 18 |
| how | 36 | 18 | 18 |
| session | 42 | 21 | 21 |
| no_answer | 30 | 15 | 15 |

session 문항은 `mode: evidence`이고 정답은 `expected_exchanges`(user 제목 줄부터 그 대화의 마지막 assistant 줄까지)다. 나머지는 `expected_pages` 하나다. no_answer는 정답이 없다.

세션 파일의 줄 번호가 정답 위치다. 세션 파일을 고치면 `questions.json`의 줄 범위도 함께 고쳐야 한다.

## 다시 내는 법

저장소 루트에서 실행한다. `<G>`는 새로 만드는 임시 Graph Home이다(기본 `~/.vault-graph`는 쓰지 않는다).

```sh
uv run --python 3.12 --all-packages --all-extras vg init --vault tests/fixtures/eval_layer2/vault --vault-id eval2 --graph-home <G>
uv run --python 3.12 --all-packages --all-extras vg index --graph-home <G>
uv run --python 3.12 --all-packages --all-extras python -m tests.benchmarks.evaluate_search \
  --questions tests/fixtures/eval_layer2/questions.json --graph-home <G> --vault-id eval2 --out-dir <out dir> [--split dev|test]
```

저장소 안에서 `vg search`를 직접 돌릴 때도 `--vault-id eval2`를 붙인다. 붙이지 않으면 현재 폴더의 프로젝트 Vault 범위로 검색해서 결과가 0개다.

기준값과 비교하려면 `tests.benchmarks.compare_search_eval`에 기준 결과와 새 `<out dir>`을 넘긴다.
