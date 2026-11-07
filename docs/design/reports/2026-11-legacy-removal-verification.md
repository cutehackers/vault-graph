# 확인 A-30(제거 뒤): 대체 경로가 없어도 vg 회상이 나온다 (2026-11-07)

spec 2026-11-05-session-memory-indexing §4.4.9 이주6, 작업 #47. 사람이 제거를 확인한 기록은 보고서 2026-11-legacy-removal-confirmation에 있다.

## 요청S11 반영

vault-builder 브랜치 `feat/jh/session-memory-requests`(`7d0bb1f..a42c1aa`, 아직 push하지 않음):

| 커밋 | 바뀐 것 |
|---|---|
| `d7146d6` | vg가 없거나 실패하면 SessionStart 훅이 `recall.sh`를 실행하지 않고 빈 출력으로 끝난다. 수집 대체(`capture --direct`)는 남는다 |
| `1267d67` | `/project-memory` 스킬과 `recall.sh`를 설치하지 않는다. 이전 설치본은 builder가 쓴 바이트와 같을 때만 지운다 |
| `3b69b88` | `maps build`가 프로젝트 요약을 만들지 않고 `maps no-project-summary` 명령이 없어진다 |
| `49f6d85` | `memory-cleanup` 스킬을 지우고 contract와 manifest schema를 6으로 올린다 |
| `9f6602b` | 옛 요약 페이지가 남은 Vault에서도 `maps build --check`가 통과한다. 이 고침이 없으면 업그레이드가 되돌려진다 |
| `cbb1c31` | 제거 메모를 구현됨으로 표시한다 |
| `a42c1aa` | vault-builder 5.0.0 |

- 기존 `wiki/maps/projects/*.md`: `generated_by: tools/wiki/cli.py maps build` 표시가 있고 잠금이 없는 페이지만 `maps build`가 지운다. 사람이 쓴 파일은 남는다.
- `memory-scan`과 `sharable`은 vg가 쓰므로 남는다.
- vault-builder 검사: `scripts/release_gate.sh --tier full`이 통과한다. `tests`는 441개, `builder_tests`는 592개(1 skip)다.

## 확인

1. vault-builder 쪽 변경 범위. `git log main..feat/jh/session-memory-requests`를 대체 경로 파일로 거른 결과:
   - 요청S4: `15bc235`
   - 요청S9: `af90200`
   - 요청S10: `9f19b1e`
   - 요청S11: 위 표의 커밋들
   - 그 밖의 변경은 없다.
2. 제거 뒤 회상. 새 훅 실행기(`assets/vault-hooks/vault_hooks.py`)를 vault-graph 저장소에서 SessionStart 입력으로 직접 돌렸다.
   - vg가 있을 때(이 브랜치 vg, Graph Home 사본): 종료 코드 0. "프로젝트 요약 / 현재 결정"으로 시작하는 vg 회상 2,753바이트가 나왔다.
   - vg가 없을 때(`PATH`에 vg 없음): 표준 출력은 0바이트다. 표준 오류에는 `vg was not found; nothing to recall.` 한 줄이 나온다. `recall.sh`는 실행되지 않는다.
3. vault-graph 회상 테스트: `pytest tests/test_session_recall.py tests/test_cli_hook_session_start.py -q`는 139개 통과다.
4. `git log main..feat/jh/session-memory-indexing`의 커밋 메시지에 `Co-Authored-By`가 0건이다. vault-builder 쪽 새 커밋도 0건이다.

## 남은 것

- vault-builder 5.0.0은 아직 push하지 않았고 이 Mac의 Vault에도 설치하지 않았다. 설치 전까지는 지금 설치본의 `recall.sh` 대체가 그대로 동작한다.
- vault-graph Vault의 결정 페이지 `sessionstart-recall-uses-vault-graph-when-installed-falls-back-to-recall-sh.md`(A-23에서 게시)는 지금 동작을 적고 있다. 5.0.0을 설치한 뒤에는 `supersede_claim`이나 `retire_memory(replaced_by=...)`로 고쳐야 한다.
- 이미 설치된 옛 훅 실행기는 바뀌지 않는다. 다만 설치가 `recall.sh`를 지우므로 옛 실행기도 빈 출력으로 끝난다.
- 기존 Vault의 `memory-cleanup` 스킬 파일은 migration이 지우지 않는다. vault-builder CHANGELOG의 Upgrade 절이 `git rm` 명령을 안내한다.
