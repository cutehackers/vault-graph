## id
33

## title
S10e 쓰기 쪽 M18: `build_supersede_claim_draft`, `build_restore_draft`, `VaultImporter` 포트, 처리 기록, `inferred` 10개 상한

## goal
claim 대체, 되살리기, L1 사본 보존의 vg 쪽 요청 만들기와 처리 기록이 있다. (Intent 6, 8)

## spec
§4.4.4 claim 대체와 처리 기록, §4.4.5 보존, §4.4.13-3, §6

## acceptance
A-38(vg 쪽), A-39(vg 쪽), A-24(vg 쪽), A-31

## files
- src/vault_graph/operation/memory/memory_drafts.py
- src/vault_graph/operation/memory/memory_ports.py
- src/vault_graph/operation/memory/memory_requests.py
- src/vault_graph/operation/memory/memory_write_service.py
- src/vault_graph/interface/composition/adapters/vault_import_cli.py (신규)
- tests/test_supersede_claim_draft.py (신규)
- tests/test_restore_draft.py (신규)
- tests/test_memory_import_port.py (신규)
- tests/test_candidate_key_recording.py (신규)

## blockers
1, 28, 요청S8(외부, 실제 `import-source` 확인은 #37)

## checks
pytest tests/test_supersede_claim_draft.py tests/test_restore_draft.py tests/test_memory_import_port.py tests/test_candidate_key_recording.py tests/test_memory_drafts.py tests/test_memory_write_boundary.py tests/test_memory_write_service.py -q

## wave
10

## done-when
- [ ] `supersede-claim`과 `restore`가 `patch-page` draft이고 publish-draft나 `review propose`로만 나간다
- [ ] `published`나 `proposed`일 때만 처리 기록을 남기고 `rejected`·`error`면 남기지 않는다
- [ ] 11번째 `inferred`가 `rejected`이고, 폐기되지 않은 페이지의 `restore`는 Vault를 부르지 않고 `rejected`다
- [ ] `import-source`를 모르는 Vault에서 `import_auto_memory`가 `error`와 "Vault 도구를 업데이트하라"를 돌려준다(가짜로 확인)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
요청S8 전에는 `VaultImporter` 가짜로 전부 만들 수 있다. vg는 Vault나 `raw/`에 직접 쓰지 않는다(A-31).
