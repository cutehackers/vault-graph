## id

15

## title

보완8 호환 경로 파일 176개를 지우고 테스트 169개 파일을 정식 경로로 옮긴다

## goal

이전 경로 별칭이 사라지고 정식 경로 하나만 남는다 (보완 계획 결정1 옵션1, spec 9절 질문2 답에 따라 추천안 채택).

## files

- 최상위 호환 경로 28개 디렉터리의 파일 176개 (삭제)
- 이전 경로를 가져오는 `tests/` 파일 169개
- 필요할 때만 `pyproject.toml`, `tests/verify_graph_module_wheels.py`, `tests/verify_release_dist.py`

## blockers

9, 10, 11, 12, 13

## acceptance

A-20, A-22

## checks

- 이전 경로 가져오기를 `grep`으로 검색 (0건)
- `uv run --python 3.12 python tests/verify_graph_module_wheels.py`
- `uv build && uv run --python 3.12 python tests/verify_release_dist.py dist`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] 테스트가 정식 경로만 가져온다
- [ ] 호환 파일 176개가 없다
- [ ] wheel과 release 검증이 통과한다
- [ ] `project-bindings.json` 관련 코드와 `vg vault add`가 남아 있다
