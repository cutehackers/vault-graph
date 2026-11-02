## id

22

## title

[vault-graph] G8b. vault-graph 설계 문서를 구현에 맞춘다

## goal

vault-graph 문서가 여러 Vault 검색, 쓰기 경로 세 개, 수집 시점, 고정 회상을 구현과 같은 내용으로 설명한다. spec Intent 8을 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `docs/html/2026-10-29-vault-memory-design.html`
- `docs/SPEC.md` (§0 현재 구현과의 차이, §2, §3, §4, §5, §6, §9.3)
- `docs/ARCHITECTURE.md` (§4)
- `docs/design/specs/2026-10-15-vault-graph-modular-architecture-ko.md` (§3 표, INV-01, INV-02, INV-05)
- `README.md` (5~17행)
- `AGENTS.md` (Project Boundary)

## blockers

13, 15, 16, 17, 18, 19, 20

## acceptance

A-25

## checks

vault-graph worktree에서 실행한다.

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_readme_onboarding_contract.py tests/test_context_pack_docs_contract.py`
- `grep -n "The only path that writes to Vault is" AGENTS.md` (0건)
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [x] 설계 HTML에서 "여러 Vault 연결은 vault-builder 몫", "검색·회상 계층", "remember 단일 쓰기" 문장이 없고, 여러 Vault 검색·표시, 추가·수정·폐기·제안, 수집 시점, 고정 회상 흐름이 있다
- [x] `docs/SPEC.md`가 A-25의 §0, §2, §3, §4, §5(MCP 14개, `vg hook capture`, 추가 허용 규칙), §6, §9.3 항목을 담는다
- [x] `docs/ARCHITECTURE.md` §4에 M18과 새 파일 위치가 있다
- [x] VG-MOD에 M18 행, INV-01 Vault 쓰기 경로 목록, 고친 INV-02 문구, INV-05 예외가 있다
- [x] README 5~17행이 장기 기억 도구와 쓰기 도구 세 개를 설명한다
- [x] AGENTS.md Project Boundary가 새 쓰기 경로 세 개(publish-draft, `review propose`, 수집 실행기)를 적는다
- [x] onboarding 계약 테스트는 고치지 않은 채 통과한다

멈춤: README 변경이 onboarding 계약 테스트를 깨면 테스트를 고치지 않고 보고한다.

기록 (2026-11-02): onboarding 계약 테스트 4개 통과(테스트 파일 무수정), AGENTS.md 옛 문장 0건, 전체 pytest 1863 passed, 7 skipped(E2E 6개는 `VAULT_BUILDER_ROOT` 없이 건너뜀). 범위 조정: SPEC §1 원칙4·§9.1, ARCHITECTURE §1·§1.1·§3.1, VG-MOD의 M01–M17 표기, `mcp_server.py` 안내문도 구현에 맞게 고쳤다.
