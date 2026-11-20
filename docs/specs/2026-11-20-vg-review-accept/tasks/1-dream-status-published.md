# 1. 발행 확인 상태 판정과 `vg dream status` 수치 수정

## id

1

## title

발행 확인 상태 판정과 `vg dream status` 수치 수정

## goal

`vg dream status`의 수락 수와 수락률이 실제로 발행된 제안만 센다. 손으로 고친 항목은 따로 보이고 고치는 방법이 나온다. (Intent의 4번째 항목)

## units

D7, I3, F1, A6

## files

- src/vault_graph/interface/composition/adapters/vault_review_queue.py
- src/vault_graph/interface/cli/dream_commands.py
- tests/test_vault_review_queue.py
- tests/test_cli_dream_status_published.py

## blockers

없음

## checks

- tests/test_vault_review_queue.py
- tests/test_cli_dream_status_published.py

## done-when

- [ ] `review_item_state(vault_root, review_path)`가 pending, accepted, unpublished, rejected, resolved, missing을 돌려준다.
- [ ] `_echo_runs`가 `sent/accepted/rejected/pending/unpublished/other`를 센다.
- [ ] 미발행 수락마다 Vault 이름, 경로, 고치는 방법을 한 줄씩 낸다.
- [ ] 수락률 분자와 분모에 미발행을 넣지 않는다.
- [ ] 대기 한도 안내 문구가 `vg review`를 가리킨다. (D10 일부, 이 파일을 쓰는 작업이 이것뿐이라 여기서 한다.)
- [ ] 실제 Vault 도구가 쓴 항목 파일로 `resolution` 읽기(R2)를 시험한다.
