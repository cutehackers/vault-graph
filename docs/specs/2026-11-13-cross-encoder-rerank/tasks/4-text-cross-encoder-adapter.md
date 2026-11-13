# 작업 4. fastembed TextCrossEncoder 어댑터와 256 토큰 자르기

## id

4

## title

fastembed `TextCrossEncoder` 어댑터와 256 토큰 자르기

## goal

preset 하나를 받아 오프라인으로 모델을 찾고 `Reranker`를 돌려주는 어댑터가 생긴다. fastembed 연결은 adapters 안에만 있고 모델 없이도 테스트할 수 있다(Intent 2).

## units

D14, I2, F6, F8, A6, A8, A9

## files

- `src/vault_graph/interface/composition/adapters/text_cross_encoder.py`
- `tests/test_text_cross_encoder.py`
- `tests/test_reranker_config.py`

## blockers

1, 2, 3

## checks

- `tests/test_text_cross_encoder.py`
- `tests/test_reranker_config.py`

## done-when

- [ ] 어댑터가 `Reranker`를 구현하고, `TextCrossEncoder`를 고정 revision 스냅숏으로 lazy하게 만든다.
- [ ] 검색 경로는 `local_files_only=True`로만 모델을 찾고, 없으면 다른 preset이나 fastembed 기본 모델로 바꾸지 않는다. 이 동작과 `vg reranker use`·`off`가 `tests/test_reranker_config.py`에서 A8로 함께 확인된다.
- [ ] `add_custom_model`은 프로세스당 한 번 잠금 아래에서만 불린다. 여러 번, 여러 스레드에서 만들어도 한 번이다. fastembed 가져오기는 adapters 안에만 있다.
- [ ] 질의와 텍스트 쌍을 256 토큰 안으로 자른다. 텍스트를 먼저 자르고, 질의가 256을 넘으면 128 토큰으로 자르며, 질의는 128 토큰보다 짧게 잘리지 않는다.
- [ ] ONNX·토크나이저·추론 오류를 `RerankError`로 바꾼다.
- [ ] 테스트는 모델을 받지 않는다.
