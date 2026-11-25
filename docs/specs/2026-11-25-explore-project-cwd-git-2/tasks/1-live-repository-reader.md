## id

1

## title

git 저장소를 직접 읽는 `LiveRepositoryReader`를 만든다

## goal

등록도 색인도 없이 git 저장소 하나에서 작업 설명에 맞는 심볼과 줄 위치 증거를 몇 초 안에 읽는다. 아무것도 쓰지 않는다. Intent의 "등록 없이 cwd의 저장소를 읽기만 한다"를 이루는 읽기 계층이다.

## units

D3, D4, D5, I1, I7, F5, F6, F7, F8, A5, A6

## files

- `src/vault_graph/project/code/live_repository_reader.py`
- `tests/test_live_repository_reader.py`

## blockers

없음

## checks

- `tests/test_live_repository_reader.py`

## done-when

- [ ] `find_repository`가 읽을 뿌리, 주 worktree 폴더 이름, HEAD revision을 돌려준다. 저장소가 아니면 None이고, commit이 없으면 revision이 None이다. git이 아예 실행되지 않는 경우와 git 밖인 경우를 service가 가릴 수 있다.
- [ ] `search`가 낱말 8개, git 명령 하나 5초, git 실행 합계 10초, 파싱 파일 50개, 파일 하나 512 KiB 상한을 지킨다. 상한에 걸리면 `partial`과 `code_live_read_truncated` 경고를 낸다.
- [ ] 파일 목록을 `git ls-files -s --cached --others --exclude-standard`로 얻고, rglob을 쓰지 않는다. symlink, submodule, 기본 제외 폴더는 건너뛴다.
- [ ] git은 `rev-parse`, `ls-files`, `grep`만 `GIT_OPTIONAL_LOCKS=0`으로 실행한다. `git status`는 실행하지 않고 저장소와 Graph Home에 쓰지 않는다.
- [ ] 건너뛴 파일 수를 `code_live_files_skipped` 경고 하나로 알리고, 경로는 상대 경로만 쓴다. 문법 오류 파일은 줄 위치 증거로 대신한다.
- [ ] 낱말이 없으면 `code_live_no_terms`, 맞는 파일이 없으면 `code_live_no_match` 경고와 함께 성공한다.
- [ ] `tests/test_live_repository_reader.py`가 A5, A6 사례와 reader 쪽 A1 사례(심볼 증거가 줄 증거보다 앞, linked worktree의 이름표)를 통과한다.
