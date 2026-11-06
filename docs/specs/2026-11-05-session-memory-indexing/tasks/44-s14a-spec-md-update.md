## id
44

## title
S14a `docs/SPEC.md` 반영: §4, §5, §6, §9.2에 새 사실과 backlog

## goal
재시도 간격, 임베딩 캐시, export 설정, MCP 19개, `include_retired`, `kind=project`, 범위 규칙이 외부 계약에 적힌다. (Intent 5, 6, 7)

## spec
§4.2.8, §4.4.2, §4.4.13, §4.5 backlog

## acceptance
A-11(backlog), A-33(SPEC 부분)

## files
- docs/SPEC.md

## blockers
1, 6, 8, 10, 17, 29, 36, 42

## checks
pytest tests/test_context_pack_docs_contract.py -q

## wave
15

## done-when
- [ ] §0 "폐기 페이지를 포함해 검색하는 옵션은 없다" 줄이 지워졌다
- [ ] §4에 재시도 간격, 임베딩 캐시, export 설정 위치가, §5에 MCP 도구 19개, `include_retired`, `kind`의 `project`가, §6에 범위 규칙과 `sharable`이 있다
- [ ] B-1(Codex adapter)과 B-2(로컬 언어 모델 단계, 결정성 규칙 포함)가 완료 조건과 함께 §9.2 n차 로드맵의 새 행으로 있다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
`docs/SPEC.md`는 #6이 먼저 수정했다(wave 2). #45와 파일이 겹치지 않는다.
