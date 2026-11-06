## id
25

## title
S6b 실제 Vault 도구로 v2 수집과 v1→v2 이어 쓰기 E2E

## goal
요청S10 결과가 이 spec의 계약을 지키는지 `VAULT_BUILDER_ROOT`로 확인한다. (Intent 2)

## spec
§4.2.5, §4.2.12, 위험A9

## acceptance
A-3, A-37

## files
- tests/e2e/test_session_capture_v2.py (신규)
- tests/e2e/test_session_v1_to_v2.py (신규)

## blockers
1, 14, 24, 요청S10(외부, 필수)

## checks
VAULT_BUILDER_ROOT=<vault-builder 경로> pytest tests/e2e/test_session_capture_v2.py tests/e2e/test_session_v1_to_v2.py -q

## wave
9

## done-when
- [ ] v2 파일 생성, 새 턴이 없으면 새 파일 없음, 열린 교환은 파일에 없음, 같은 입력의 같은 바이트
- [ ] `--normalized`를 모르는 Vault 도구에서 v1 파일과 훅 종료 코드 0
- [ ] v1 파트 2 뒤 파트 3이 v2이고 `continued=1`이 있으며 턴 uuid 집합에 빠짐·겹침이 없다
- [ ] `--recapture`가 가장 높은 번호 + 1부터 쓰고 기존 파일 sha256이 같으며, 색인 결과에서 겹친 v1 교환이 빠진다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
요청S10이 없으면 시작할 수 없다. 그 전에는 #14의 가짜 실행기 테스트가 vg 쪽을 이미 덮는다.
