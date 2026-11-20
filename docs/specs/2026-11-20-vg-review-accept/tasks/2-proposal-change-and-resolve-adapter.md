# 2. 바뀌는 글 계산과 Vault `review resolve` 어댑터

## id

2

## title

바뀌는 글 계산과 Vault `review resolve` 어댑터

## goal

제안마다 바뀌는 글을 만들 수 있고, Vault의 `review resolve --json` 결과만 믿는 실행 어댑터가 생긴다. (Intent의 "수락 전에 바뀌는 글을 본다"와 "수락은 Vault가 처리한 것만 센다")

## units

D4, D9, I5, F2, F3, F4, F5, A3, A2

## files

- src/vault_graph/operation/memory/proposal_change.py
- src/vault_graph/interface/composition/adapters/vault_review_cli.py
- tests/test_proposal_change.py
- tests/test_vault_review_cli.py

## blockers

없음

## checks

- tests/test_proposal_change.py
- tests/test_vault_review_cli.py

## done-when

- [ ] `proposal_change.py`가 파일을 읽지 않는 순수 함수다.
- [ ] 새 페이지는 전체 글, 기존 페이지 upsert는 본문 diff와 달라지는 frontmatter 키를 낸다.
- [ ] `patch-page`는 초안에 적힌 대로 보이고 결과 페이지를 계산하지 않는다.
- [ ] 근거 줄을 뽑고 한국어가 깨지지 않는다.
- [ ] 어댑터가 `review resolve <path> --status <s> --resolution <text> --json`을 Vault 폴더에서 실행하고 `status`, `reason`, `written_paths`, `messages`만 읽는다.
- [ ] 시간 한도는 `PUBLISH_TIMEOUT_SECONDS`를 쓴다.
- [ ] resolved가 아닌 모든 결과는 실패이고, 실패를 수락으로 알리지 않는다.
- [ ] `target-changed`, 종료 코드 2, JSON이 아닌 출력, 시간 초과, 파일 없음에 정해진 안내가 붙는다.

## notes

A2는 작업 2와 3 둘 다 units에 있다. 이 작업은 `tests/test_proposal_change.py` 쪽을 맡고, `tests/test_cli_review.py`는 작업 3이 쓴다.
