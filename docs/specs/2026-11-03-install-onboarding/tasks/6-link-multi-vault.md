# 6. link 여러 Vault 지원과 link 안내 문구

## id

6

## title

`link`가 Vault 이름 여러 개와 이름 생략을 받게 하고, recall과 router의 link 안내를 `vault-builder link ...`로 바꾼다 (vault-builder)

## goal

명령 하나로 저장소 하나를 필요한 Vault 전부에 연결한다(spec Intent "저장소 하나 연결 = 명령 하나", 발견3, 발견9, §4.5).

## files

저장소: vault-builder, worktree `$HOME/workspace/vault-builder/.worktrees/feat-jh-install-update` (branch `feat/jh/install-update`). 모든 작업과 검사는 이 worktree에서 한다. main checkout에서는 하지 않는다.

- `tools/vault_migration/linking.py`
- `tools/vault_migration/cli.py` (`link` parser)
- `tools/vault_migration/assets/project-memory/scripts/recall.sh` (86행 안내)
- `tools/vault_migration/assets/llm-wiki-router/llm_wiki_router.py` (56행 안내)
- `builder_tests/test_link_multi.py` (새 파일)
- `builder_tests/test_vault_migration.py` (6958행 recall 안내 기대값)
- `builder_tests/test_llm_wiki_router.py` (router 안내 문구를 기대하는 테스트가 실패할 때만 고친다)

## blockers

- 5 (`linking.py`를 함께 쓰고, 역할 목록이 필요하다)

## acceptance

- A-8
- A-9
- A-10
- A-12 (link 부분)
- A-14 (자동 기본값이 정해지지 않는 부분)
- A-30

## checks

worktree 루트에서 실행한다.

- `python3 -m unittest builder_tests.test_link_multi builder_tests.test_llm_wiki_router builder_tests.test_vault_migration -v`
- `scripts/release_gate.sh`

## done-when

- [ ] 이름을 여러 개 주면 `vault-map.json`을 한 번 읽고 한 번 쓴다.
- [ ] 기본 쓰기 Vault 규칙은 모두 더한 뒤 한 번만 적용한다.
- [ ] 이름을 생략하면 다음처럼 동작한다.
  - [ ] per_repo가 아닌 역할의 Vault와 표에 없는 역할의 Vault를 연결한다.
  - [ ] project Vault는 연결하지 않는다.
  - [ ] project Vault 연결 명령 `vault-builder link <이름> --repo <경로>`를 한 줄로 안내한다.
- [ ] 표에 없는 역할의 Vault를 연결하면 "알려진 역할이 아니다, 공유 Vault로 연결한다"는 줄을 출력한다.
- [ ] 이름 하나를 주는 기존 사용법은 출력과 결과가 같다. 기존 테스트가 통과한다.
- [ ] recall.sh의 "연결되지 않은 저장소" 안내가 `vault-builder link ...`다.
- [ ] `llm_wiki_router.py`의 link 안내가 `vault-builder link ...`다.
- [ ] 문구 변경 때문에 실패한 테스트의 기대값을 고쳤다.
