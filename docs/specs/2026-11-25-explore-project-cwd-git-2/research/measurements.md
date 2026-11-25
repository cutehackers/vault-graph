# 코드 투영 측정 결과

측정일: 2026-11-25. 대상: 이 저장소(vault-graph). 측정은 이 spec을 요청한 부모 세션이 했고, brief에 M1, M2로 적었다. 이 spec 작성 중에는 다시 재지 않았다.

### X11. 이 저장소 전체 코드 투영은 약 25초가 걸리고 97 MB를 쓴다
- source: brief 측정 M1(2026-11-25 부모 세션, 기존 `CodeProjectionService` 실행)

추적 파일 중 `.py`, `.dart` 684개를 투영하는 데 약 25초가 걸렸고 Graph Home에 97 MB를 썼다. MCP 호출마다 투영을 만들기에는 너무 느리다.

### X12. 기존 스캐너는 일반 Python checkout에서 `.venv` symlink 때문에 실패한다
- source: brief 측정 M2(2026-11-25 부모 세션), `src/vault_graph/project/code/source_scanning.py:79-84@fd21e3f`, `source_scanning.py:136-144@fd21e3f`, `src/vault_graph/project/code/repository_catalog.py:281@fd21e3f`
- basis: X7

`_walk_files`는 `root.rglob("*")`로 추적되지 않는 `.venv`까지 걷고, 제외 규칙보다 symlink 검사를 먼저 한다. 그래서 `CodeSourceScanError: source symlink escapes repository root: .venv/bin/python -> ...`로 멈춘다. 등록 검증(`_validate_entry_policy`)도 모든 symlink를 rglob으로 훑는다. 지금 등록 경로는 이 저장소에 그대로 쓸 수 없다. 코드 줄 번호는 이 spec 작성 중에 확인했다.
