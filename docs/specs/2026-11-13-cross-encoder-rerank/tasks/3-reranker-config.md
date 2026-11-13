# 작업 3. 재정렬 preset, 설정, vg reranker use/off

## id

3

## title

재정렬 preset, `configs/reranker.json` 설정, `vg reranker use/off`

## goal

사용자가 `vg reranker use mmarco`로 모델을 받고 재정렬을 켜고 끌 수 있다. 내려받기는 이 명령에서만 일어난다(Intent 2, 3).

## units

D5, D9, D10, D18, A19

## files

- `src/vault_graph/interface/composition/adapters/rerank_presets.py`
- `src/vault_graph/operation/scope/reranker_selection.py`
- `src/vault_graph/interface/cli/reranker_commands.py`
- `src/vault_graph/interface/cli/main.py`
- `tests/test_reranker_config.py`

## blockers

1

## checks

- `tests/test_reranker_config.py`

## done-when

- [ ] `RERANK_PRESETS`에 mmarco의 `onnx/model_qint8_arm64.onnx` 항목 하나만 있고 고정 revision, 파일 목록, 크기를 가진다. bge와 다른 모델은 없다.
- [ ] `configs/reranker.json`(`version`, `enabled`, `model`)을 읽고 쓰는 코드가 있다. 파일이 없으면 꺼짐이다. 모델 폴더는 `embedding.json`의 `models_dir`(기본 `~/llm/models`)를 같이 쓴다.
- [ ] `vg reranker use <preset>`이 고정 revision 파일을 받고 성공한 뒤에만 설정에 켜짐과 preset을 쓴다. 이미 받은 파일은 다시 받지 않는다. `vg reranker off`는 `enabled`만 끈다.
- [ ] 검색, 색인, 서버 시작, 모듈 가져오기는 모델을 받지 않는다.
- [ ] 테스트는 네트워크 없이 통과한다. 다운로드 호출은 가짜로 대체한다.
