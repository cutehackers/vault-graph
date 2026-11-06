# 확인 A-20·A-29: 이 컴퓨터 vault-map.json으로 본 회상 범위 규칙 (2026-11-06)

spec 2026-11-05-session-memory-indexing, 작업 #16. 코드: `e640d9b`(범위 규칙 `page_in_project`, `sharable`). vault-builder 요청S4(`sharable` 설정 명령)는 아직 반영 전이다. 이 컴퓨터의 vault-map.json에는 `sharable` 값이 없다.

## 방법

vault-graph 저장소 폴더를 `cwd`로 한 같은 SessionStart 입력을 두 vg에 넣었다. 하나는 설치된 릴리스 vg이고, 하나는 이 브랜치의 vg다. 둘 다 실제 Graph Home과 실제 Vault를 읽었다.

## 결과

| 회상 | 항목 수 | personal Vault | vault-graph Vault | 표준 오류 |
|---|---|---|---|---|
| 릴리스(변경 전) | 18 | 18 | 0 | 없음 |
| 이 브랜치(변경 뒤) | 7 | 0 | 7 | personal의 `sharable` 미설정 안내 1줄 |

- 변경 전에는 다른 프로젝트(sgp-981-app, bake 등)의 personal 기억이 vault-graph 세션에 들어갔다(발견D1). 변경 뒤에는 들어가지 않는다.
- vault-graph Vault는 이 프로젝트 하나에만 연결되어 있다. 그래서 `project`가 없는 페이지 17쪽이 이 프로젝트 기억으로 들어온다. 리뷰1이 지적한 "회상이 빈다"는 일어나지 않는다.
- vg 경로 회상과 `recall.sh` 경로 회상이 모두 비어 있지 않다(A-29). `recall.sh`는 이 단계에서 바뀌지 않았다.

## 위험D13: 프로젝트 Vault의 표시 없는 페이지

- vault-graph Vault `wiki/` 17쪽 중 다른 프로젝트 이야기를 담은 페이지는 0쪽이다.
- 17쪽은 모두 Vault 템플릿이 만든 일반 페이지다(Inbox, Wiki Linting, Compiled Knowledge 등). vault-graph에 대한 실제 결정은 이 Vault에 없다.

## 위험D4: 실제로 일어난 영향

- personal Vault에 vault-graph를 다루는 결정 페이지 6쪽이 있고, 6쪽 모두 `project`가 없다. 이 페이지들은 이제 vault-graph 세션 시작 회상에 나오지 않는다. 검색(`vg search`, `search_vault`)에는 그대로 나온다.
- spec 결정25대로 미설정은 false로 다루고 안내 한 줄을 낸다. 사람이 고를 수 있는 길은 둘이다.
  1. personal Vault에 `"sharable": true`를 둔다. personal의 표시 없는 페이지가 모든 연결 프로젝트 회상에 다시 들어간다(변경 전과 같은 섞임).
  2. 그 6쪽을 vault-graph 프로젝트 기억으로 옮긴다. `curate_memory` 정리(작업 #36)나 `update_memory`로 project Vault에 다시 쓴다.
