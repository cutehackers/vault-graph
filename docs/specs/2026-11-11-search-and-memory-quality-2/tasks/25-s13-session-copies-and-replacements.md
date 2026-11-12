# 25. S13 세션 교환 사본 접기와 대체된 페이지 근거

## id
25

## title
같은 Vault의 세션 교환 사본을 접고, 대체된 페이지를 근거로 붙인다

## goal
같은 대화를 이어 쓴 세션 파일의 같은 교환이 상위 자리를 여러 번 차지하지 않는다. 옛 결정을 묻는 질문에서 대체된 페이지가 사라지지 않는다. 의도2를 담당한다(결정17).

## files
- src/vault_graph/retrieval/search/evidence_result_assembly.py
- tests/ 아래 새 테스트 파일

## blockers
10

## acceptance
A-16

## checks
- `uv run --python 3.12 pytest -q`
- 층1 평가 실행 후 비교 명령으로 기준값과 비교
- 층2 평가 실행 후 비교 명령으로 기준값과 비교
- `uv run --python 3.12 ruff check src tests`

## done-when
- [ ] 같은 Vault 안 내용이 같은 세션 교환은 가장 높은 사본 자리에 결과 하나로 접힌다.
- [ ] supersedes로 대체된 페이지는 남은 결과의 근거로 붙고, 결과 목록에서 버려지지 않는다.
- [ ] 층1 시험용 recall@5가 떨어지지 않고 층2 모든 종류가 떨어지지 않는다.
