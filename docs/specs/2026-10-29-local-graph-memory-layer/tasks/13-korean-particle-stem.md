## id

13

## title

1차-5 한국어 조사를 뗀 `body_stem` 열을 키워드 색인에 추가한다

## goal

"결정"으로 검색하면 본문의 "결정을"이 맞는다. 한글이 없는 질의의 결과는 그대로다. spec Intent 5와 S7을 다룬다.

## files

- `src/vault_graph/storage/local/korean_particle.py` (새 파일: `strip_korean_particle`, Vault `tools/wiki/lib/search.py:116`의 조사 목록 복사와 출처 주석)
- `src/vault_graph/storage/local/sqlite_keyword_index.py` (FTS 열 추가, 기록 경로, `_match_query`와 `_query_tokens`, `KEYWORD_SCHEMA_VERSION` 올림)
- `src/vault_graph/operation/diagnostics/index_status_reader.py` (오래된 형식 경고. 실제 위치는 구현 시 확인)
- `docs/DECISIONS.md` (S7, INV-05 예외)
- `tests/test_korean_particle.py`
- `tests/test_keyword_index_korean.py`

결정 (2026-10-30 승인): 새 모듈 이름은 `korean_particle.py`로 쓴다. DECISIONS에는 이 작업에서 S7(INV-05 예외)만 적는다. 결정4·6·7·8·9·10·11은 작업 1에서 적었다.

Vault `search.py`는 읽기만 한다.

## blockers

3

## acceptance

A-17, A-18, A-20

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_korean_particle.py tests/test_keyword_index_korean.py tests/test_search_read_only_boundary.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests -k keyword`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] 단위 테스트에서 "결정을"은 "결정", "결정"은 "결정", "책을"은 "책을", "GraphRAG"는 그대로다
- [ ] 본문에 "결정을"만 있는 문서가 질의 "결정"과 "결정은"으로 검색되고, "결정론"만 있는 문서는 질의 "결정"으로 검색되지 않는다
- [ ] 한글이 없는 기존 fixture 질의의 문서, 점수, 순서가 `28f1c96`과 같다
- [ ] 색인 세대 버전이 올라갔다
- [ ] 옛 형식 Graph Home에서 `vg status`가 `vg index --full`이 필요하다고 경고하고, 검색은 기존 열로 동작하며 자동으로 다시 색인하지 않는다
- [ ] `vg index --full` 뒤에는 한글 검색이 A-17대로 동작한다
- [ ] `docs/DECISIONS.md`에 INV-05 예외가 "측정1 적중률이 기준선보다 낮아지지 않음" 조건과 함께 적혀 있다
