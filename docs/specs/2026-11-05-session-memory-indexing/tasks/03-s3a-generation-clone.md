## id
3

## title
S3a 세대 준비를 `clone_tree`(APFS clone)로 바꾼다

## goal
증분 run이 세대를 `copytree`로 650MB 복사하지 않고 APFS clone으로 만든다. (Intent 5)

## spec
§4.3.3 첫째, 위험B3

## acceptance
A-18(clone 부분)

## files
- src/vault_graph/indexing/publication/projection_generation.py
- src/vault_graph/indexing/publication/tree_clone.py (신규)
- tests/test_tree_clone.py (신규)
- tests/test_projection_generation_clone.py (신규)

## blockers
1

## checks
pytest tests/test_tree_clone.py tests/test_projection_generation_clone.py tests/test_projection_generation.py tests/test_projection_generation_lock.py -q

## wave
2

## done-when
- [ ] 준비 뒤 스테이징 SQLite를 고쳐도 활성 세대 sha256이 같다
- [ ] `clonefile` 실패를 주입하면 `copytree`로 돌아가고 경고 한 줄이 나온다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
디스크 증가량 측정은 #12(사람 컴퓨터).
