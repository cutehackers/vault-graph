# 2. 실행기 결과에서 exchange_count를 읽고 recapture_session에 hook_cwd 인자를 더한다

## id
2

## title
실행기 결과에서 exchange_count를 읽고 recapture_session에 hook_cwd 인자를 더한다

## goal
migrate가 교환 수를 대조하고 상위 폴더 cwd를 넘길 수 있다. 기본값이면 기존 동작이 그대로다. export의 `--recapture`와 같은 경로를 공유하므로 호환 범위를 지킨다.

## units
- D4

## files
- src/vault_graph/interface/composition/adapters/session_capture_runner.py
- src/vault_graph/interface/composition/adapters/vault_capture_cli.py
- tests/test_session_capture_runner_options.py

## blockers
(none)

## checks
- tests/test_session_capture_runner_options.py
- tests/test_cli_session_recapture.py
- tests/test_cli_session_export.py

## done-when
- [ ] `CaptureOutcome.exchange_count: int | None`을 결과 JSON에서 읽고, 없으면 None이다
- [ ] `recapture_session(..., hook_cwd=None)`이 주어지면 훅 JSON `cwd`만 바꾸고 정규화 파일은 그대로다
- [ ] 기본값이면 훅 JSON과 인자가 기존과 같다
- [ ] 기존 `test_cli_session_recapture.py`, `test_cli_session_export.py`를 고치지 않고 통과한다
