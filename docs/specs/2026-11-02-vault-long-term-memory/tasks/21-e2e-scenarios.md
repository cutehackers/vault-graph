## id

21

## title

[vault-graph] G8a. 시나리오 ①~⑥ E2E 테스트를 만든다

## goal

실제 Vault 도구로 장기 기억의 여섯 가지 성공 시나리오가 동작함을 증명한다. spec Intent 1~6, 결정7을 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `tests/e2e/test_long_term_memory_scenarios.py` (새 파일)
- `tests/e2e/conftest.py` (필요할 때만, 새 파일)

## blockers

10, 13, 15, 16, 17, 18, 19, 20

## acceptance

A-1, A-2, A-3, A-4, A-5, A-6, A-24

## checks

vault-graph worktree에서 실행한다. vault-builder 검사는 `$HOME/workspace/vault-builder`에서 실행한다.

- `VAULT_BUILDER_ROOT=$HOME/workspace/vault-builder uv run --python 3.12 --all-packages --all-extras pytest -q tests/e2e/test_long_term_memory_scenarios.py` (출력 로그를 저장)
- `uv run --python 3.12 --all-packages --all-extras pytest -q`
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [ ] A-1~A-6이 시나리오마다 테스트 하나로 있고, 건너뜀 없이 통과한다
- [ ] 테스트는 `VAULT_BUILDER_ROOT`의 vault-builder로 임시 HOME 아래에 Vault를 만들고, 임시 `vault-map.json`과 임시 Graph Home만 쓴다
- [ ] 실제 Vault 도구를 하위 프로세스로 부르고 가짜 포트를 쓰지 않는다
- [ ] 변수를 설정하고 실행한 로그가 완료 증거로 남아 있다(위험11)

멈춤: vault-builder 계약이 spec과 달라 실패하면, 여기서 vault-builder를 고치지 않고 보고한다.
