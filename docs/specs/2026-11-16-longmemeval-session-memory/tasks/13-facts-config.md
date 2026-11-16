# 13. facts-config

## id
13

## title
사실 추출 설정, 추출기 포트와 선택, `vg facts on|off|status`를 만든다

## goal
추출 켜기·끄기와 추출기 고르기가 되고, 테스트가 실제 추출기를 못 부른다. Intent 3을 맡는다. 설정 파일 읽기·쓰기는 `operation/scope/`(M01, `session_export_settings.py`의 선례)에 두고, 포트와 선택 함수는 `interface/composition/adapters/`에 둔다(docs/ARCHITECTURE.md §1, §3.1).

## units
D18, D19, F13, A17

## files
- src/vault_graph/operation/scope/facts_settings.py
- src/vault_graph/interface/composition/adapters/fact_extractor.py
- src/vault_graph/interface/composition/adapters/fact_extractor_selection.py
- src/vault_graph/interface/cli/facts_commands.py
- src/vault_graph/interface/cli/main.py
- tests/conftest.py
- tests/test_facts_config.py

## blockers
9, 10, 20

## checks
- tests/test_facts_config.py

## done-when
- [ ] `configs/facts.json`(`version`, `enabled`, `extractor`, `endpoint`, `model`)을 읽고 쓰는 모듈이 있다
- [ ] 파일이 없으면 `claude`로 켜짐이다. 깨진 파일은 꺼짐이고 `status`에 이유가 나온다
- [ ] `vg facts off`는 `enabled: false`를 쓰고, `on --extractor llama-server`는 로컬을 고른다
- [ ] `status`가 대기열과 실패를 보인다
- [ ] 포트 `FactExtractor`와 선택 함수가 한 곳에 있다. 14번 어댑터는 선택 함수가 지연 가져온다
- [ ] `tests/conftest.py` 공용 설정이 선택 함수를 가짜 추출기로 바꾸고, 실제 추출기 어댑터를 부르면 실패한다
- [ ] 로컬 기본값 전환은 22번 task 측정 뒤에만 한다
- [ ] `tests/test_feature_import_direction.py`와 `tests/test_grouped_module_layout.py`가 통과한다
