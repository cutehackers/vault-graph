# 측정 A-12: 실제 Graph Home에서 벡터 색인 복구 (2026-11-06)

spec 2026-11-05-session-memory-indexing, 작업 #7. 코드: `feat/jh/session-memory-indexing`의 S0(`8831f9f`), #2(`9857af8`), #3(`46d01e6`), #4(`6d64e37`)까지.

## 배경

S0 전에는 세션 시작 백그라운드 `vg index`가 Chroma `collection.get(include=["metadatas"])`에서 `too many SQL variables`로 실패했다. 컬렉션 행 수가 33,065개로 SQLite 변수 한도 32,766을 넘었기 때문이다. 2026-11-05 10:12 뒤의 세션 기록은 벡터 검색에 들어가지 않았다.

## 실행

`vg index --vault-id vault-graph` 1회. 이 Mac의 실제 Graph Home.

| 항목 | 값 |
|---|---|
| 종료 코드 | 0 |
| 바뀐 문서 / 그대로 | 11 / 43 |
| 벡터 upsert | 2,154 (밀려 있던 새 조각) |
| 벡터 그대로 | 18,191 |
| 벡터 실패 | 없음. 실패 기록 파일이 생기지 않음 |
| 실행 시간 | 28.9초 |
| 최대 RSS | 4.75GB |
| 새 세대 발행 | 됨 (활성 세대 id가 바뀜) |

## 판단

- A-12 측정 조건 "`vg index --vault-id vault-graph`가 성공하고 벡터 revision이 바뀐다"를 충족했다.
- 위험B1은 S0 단위 테스트에서 확인했다. 33,000행 임시 컬렉션에서 limit 없는 `get`이 같은 오류를 냈고, 페이지 조회는 모든 행을 돌려줬다.
