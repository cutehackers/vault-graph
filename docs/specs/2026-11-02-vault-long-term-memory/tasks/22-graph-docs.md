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

- [ ] 설계 HTML에서 "여러 Vault 연결은 vault-builder 몫", "검색·회상 계층", "remember 단일 쓰기" 문장이 없고, 여러 Vault 검색·표시, 추가·수정·폐기·제안, 수집 시점, 고정 회상 흐름이 있다
- [ ] `docs/SPEC.md`가 A-25의 §0, §2, §3, §4, §5(MCP 14개, `vg hook capture`, 추가 허용 규칙), §6, §9.3 항목을 담는다
- [ ] `docs/ARCHITECTURE.md` §4에 M18과 새 파일 위치가 있다
- [ ] VG-MOD에 M18 행, INV-01 Vault 쓰기 경로 목록, 고친 INV-02 문구, INV-05 예외가 있다
- [ ] README 5~17행이 장기 기억 도구와 쓰기 도구 세 개를 설명한다
- [ ] AGENTS.md Project Boundary가 새 쓰기 경로 세 개(publish-draft, `review propose`, 수집 실행기)를 적는다
- [ ] onboarding 계약 테스트는 고치지 않은 채 통과한다

멈춤: README 변경이 onboarding 계약 테스트를 깨면 테스트를 고치지 않고 보고한다.
