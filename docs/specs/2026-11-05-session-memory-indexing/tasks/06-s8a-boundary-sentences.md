## id
6

## title
S8a `AGENTS.md`, `docs/SPEC.md`에 경계 문장 10개와 §0 규칙5 예외 반영

## goal
이후 기억 관리 코드가 지켜야 할 경계가 문서에 먼저 있다. 이 커밋이 S8의 첫 커밋이다. (Intent 6)

## spec
§4.4.8 문장1~10, §4.4.4 예외 문장

## acceptance
A-10, A-33(문장 부분)

## files
- AGENTS.md
- docs/SPEC.md

## blockers
1

## checks
pytest tests/test_context_pack_docs_contract.py -q
그리고 src/ 에서 `derived`, `LocalLanguageModel` 검색 결과 0건

## wave
2

## done-when
- [ ] 문장1~10과 §0 규칙5 예외가 `AGENTS.md`와 `docs/SPEC.md`에 있다
- [ ] 원칙1 문장은 문장6 보충 말고 바뀌지 않았다
- [ ] `src/`에 로컬 언어 모델 포트, `derived` 조각, `--no-derived` 옵션이 없다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
문서만 쓰므로 요청S4와 무관하다. `docs/SPEC.md`는 #44도 쓰며 #44가 이후 wave다. 이 커밋이 S8 묶음(#6, #10, #11, #16)의 첫 커밋이어야 한다(A-10).
