## id
27

## title
S10a L1 읽기와 `memory-scan`: `auto_memory_reader`, `memory-scan --json` 읽기 전용 실행

## goal
반영되지 않은 L1 노트를 찾을 수 있다. (Intent 6)

## spec
§4.4.5 읽기와 반영 판정, §6 L1 행, 위험D1

## acceptance
A-24(어댑터 부분), A-31

## files
- src/vault_graph/interface/composition/adapters/auto_memory_reader.py (신규)
- src/vault_graph/interface/composition/adapters/memory_scan_runner.py (신규)
- tests/test_auto_memory_reader.py (신규)
- tests/test_memory_scan_runner.py (신규)

## blockers
1, 18, 24

## checks
pytest tests/test_auto_memory_reader.py tests/test_memory_scan_runner.py tests/test_vector_indexing_read_only_boundary.py -q

## wave
9

## done-when
- [ ] `CLAUDE_CONFIG_DIR`와 `autoMemoryDirectory` 각각으로 고정 L1 폴더를 찾는다
- [ ] vg 판정과 `memory-scan` 결과가 다르면 Vault 결과를 쓰고 경고 한 줄이다
- [ ] L1 폴더 파일의 sha256과 mtime이 변하지 않는다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
S10 묶음이며 spec 선행은 S9, S5, 요청S8이다. 이 task는 요청S8(`import-source`)이 필요 없다. 실제 L1 폴더와의 비교는 S11 평가 때 한다(위험D1).
