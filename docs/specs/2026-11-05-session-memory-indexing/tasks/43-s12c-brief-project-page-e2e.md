## id
43

## title
S12c brief 작성과 갱신 E2E

## goal
brief가 실제 Vault에 생기고 다음 회상 구획L3 앞에 나온다. (Intent 6, 7)

## spec
§4.4.7, 위험D5

## acceptance
A-27(S12), A-35(E2E), A-29(S12)

## files
- tests/e2e/test_brief_project_page.py (신규)

## blockers
1, 41, 42, 요청S9(외부, 필수)

## checks
VAULT_BUILDER_ROOT=<vault-builder 경로> pytest tests/e2e/test_brief_project_page.py -q

## wave
15

## done-when
- [ ] 첫 `remember(kind="project")`로 brief가 생기고 두 번째는 `rejected`이며 `update_memory`는 된다
- [ ] `update_memory` 뒤 다시 색인하면 안내 줄과 후보가 사라지고, 건너뛰면 후보만 사라진다
- [ ] 계산 전후 Vault 파일 sha256이 같다
- [ ] vg 경로와 `recall.sh`(brief를 읽도록 바뀐 것) 경로의 첫 줄 확인 기록을 PR에 남긴다(A-29)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
요청S9가 없으면 시작할 수 없다.
