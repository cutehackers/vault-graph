## id
37

## title
S10h 실제 Vault 도구로 정리 쓰기 E2E

## goal
claim 대체, import-source, 되살리기가 실제 Vault 검증을 통과한다. 위험D12도 여기서 확인한다. (Intent 6, 8)

## spec
§4.4.5, §4.4.13, 위험D12

## acceptance
A-24(E2E), A-38, A-39(E2E)

## files
- tests/e2e/test_memory_curation_write.py (신규)

## blockers
1, 36, 요청S8(외부, 필수). 요청S12(조건부): `restore_memory`가 거부되면 필요

## checks
VAULT_BUILDER_ROOT=<vault-builder 경로> pytest tests/e2e/test_memory_curation_write.py -q

## wave
12

## done-when
- [ ] `supersede_claim`이 옛 행을 `superseded`로 바꾸고 다른 행과 본문은 바이트가 같으며, 다음 회상에 옛 행 문장이 없다
- [ ] `import_auto_memory`가 `raw/imports/claude-memory/` 경로를 돌려주고, 재전송은 새 파일이 없으며 L1 파일 sha256과 mtime이 같다
- [ ] `restore_memory`가 frontmatter만 바꾼다. 거부되면 요청S12를 내야 한다는 판단을 사람에게 올린다(위험D12)
- [ ] brief 후보 키가 같은 날 두 번째 결정이 생기면 바뀐다(A-38)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
요청S8이 없으면 시작할 수 없다. 첫 E2E로 위험D12를 확인한다.
