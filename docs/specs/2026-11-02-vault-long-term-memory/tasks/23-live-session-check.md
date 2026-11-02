## id

23

## title

[두 저장소, 수동] G9. 실제 Claude Code 세션 하나로 수동 확인한다

## goal

사용자 컴퓨터의 실제 세션에서 고정 회상, 기억 쓰기, 제안 대기, 원문 수집, 검색 표시가 동작함을 확인한다. spec Intent 1~6, 결정7을 다룬다.

## files

저장소 파일은 쓰지 않는다. 사용자 컴퓨터에서 바뀌는 곳은 다음과 같다.

- `$HOME/.claude/settings.json` (훅 항목)
- `$HOME/.claude/vault-builder/` (`vault_hooks.py`, `vault-hooks.json`)
- project Vault `$HOME/vaults/vault-graph` (`wiki/`, `scratch/review/`, `raw/sessions/`)

## blockers

9, 11, 21, 22

## acceptance

A-7, 위험2, 위험3, 위험10

## checks

수동 작업이다.

- 사용자 확인을 받은 뒤 `$HOME/workspace/vault-builder`에서 `install --with-hooks`를 실행한다
- 실제 Claude Code 세션 하나에서 A-7의 다섯 항목을 확인한다
- 긴 세션을 끝낸 뒤 `$HOME/vaults/vault-graph/raw/sessions/`의 part 파일 수를 센다(위험2)

## done-when

- [ ] `$HOME/.claude/settings.json` 훅 설치 직전에 사용자 확인을 한 번 더 받았다(2026-11-02 spec 승인 조건)
- [ ] 세션 시작 문맥에 `## 고정 기억`이 있다(위험3)
- [ ] 사실 하나를 기억하라고 말하면 Vault에 페이지가 생긴다
- [ ] 추론 사실 하나가 `scratch/review/`에 대기한다
- [ ] 세션을 끝내면 `raw/sessions/`에 원문 파일이 생긴다
- [ ] 검색 결과에 Vault 이름·종류가 붙는다
- [ ] 비밀값을 뺀 결과 요약을 vault-graph PR 설명용으로 사용자에게 전달했다

멈춤: 사용자 확인이 없으면 설치하지 않는다. 다섯 항목 중 하나라도 실패하면 고치지 않고 보고한다.
