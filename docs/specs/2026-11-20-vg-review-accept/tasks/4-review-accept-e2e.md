# 4. 실제 vault-builder 도구로 수락·거절 e2e

## id

4

## title

실제 vault-builder 도구로 수락·거절 e2e

## goal

`vg review accept`와 `reject`가 실제 Vault 도구에서 끝까지 도는 것을 확인한다. (Intent의 "수락한 기억은 발행되고 검색에 나온다")

## units

A9

## files

- tests/e2e/test_review_accept.py

## blockers

3

## checks

- tests/e2e/test_review_accept.py

## done-when

- [ ] 기존 `test_long_term_memory_scenarios.py`와 같은 방식으로 Vault를 만든다.
- [ ] 수락하면 대상 페이지가 생기고 `resolution`에 "Published:"가 있으며 상태 판정이 `accepted`다.
- [ ] 색인이 끝나면 그 페이지가 검색에 나온다.
- [ ] `reject --reason`으로 거절하면 페이지가 생기지 않는다.
- [ ] 테스트가 `status`만 손으로 `accepted`로 고친 항목은 `unpublished`로 판정된다.
