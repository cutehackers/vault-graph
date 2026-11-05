# Spec: PyPI 배포를 없애고 git 태그와 GitHub Release로 배포

- spec id: 2026-11-05-git-tag-release
- task: 20261105-redesign-publishing-arou-b866
- base: main @ e764c7a, branch bake/git-tag-release

## 1. Problem

배포 절차는 PyPI 업로드를 중심으로 짜여 있지만, 실제 설치는 PyPI를 쓰지 않는다.

1. 설치 경로는 git이다.
   - vault-builder 설치 명령은 `uv tool install --force --python 3.12 git+<VAULT_GRAPH_REPO>`로 vg를 설치하고, 기본 주소는 `https://github.com/cutehackers/vault-graph.git`다. `vault-builder/tools/vault_migration/onboarding.py:8,42,257`, 테스트 `vault-builder/builder_tests/test_onboarding_setup.py:245,475`. 주소에 ref가 없으므로 `main`이 설치된다.
   - README "Install `vg` only"도 같은 git 주소를 쓴다. `README.md:58-61@e764c7a`
   - README는 PyPI 최신 버전 0.2.1에 설치 명령이 쓰는 명령(`vg mcp unregister` 등)이 없다고 적는다. `README.md:46-49@e764c7a`
2. 그런데 배포 절차는 PyPI 업로드를 위해 단계가 셋이다.
   - `publish.sh`가 버전 올림 PR을 연다. `publish.sh:1-135@e764c7a`
   - `prepare-release`(수동 실행)가 버전 일치, 태그 미사용, lint, mypy, test, 모듈 wheel 검사, `uv build`, `twine check`, `verify_release_dist.py`를 실행하고 `dist/*`를 첨부한 draft Release를 만든다. `.github/workflows/prepare-release.yml:1-114@e764c7a`
   - 사람이 draft를 publish하면 `publish-pypi`가 같은 검사를 다시 돌리고 `pypi` environment 승인 뒤 PyPI에 올린다. `.github/workflows/publish-pypi.yml:1-43@e764c7a`
   - `publish-testpypi`는 수동 TestPyPI 업로드다. `.github/workflows/publish-testpypi.yml:1-42@e764c7a`
3. 그 결과 v0.3.0은 버전 올림(e764c7a)까지 병합됐지만 태그 `v0.3.0`도 Release도 없다(brief 기록). 지금 절차대로 끝내려면 아무도 쓰지 않는 PyPI 업로드까지 승인해야 한다.
4. wheel 빌드 검사는 배포 workflow에만 있다. `ci.yml`은 ruff, mypy, pytest만 돈다(`.github/workflows/ci.yml:13-23@e764c7a`, `docs/DECISIONS.md:796-804@e764c7a`). git 설치도 같은 소스에서 같은 wheel을 빌드하므로 이 검사는 PyPI를 없애도 어딘가에 남아야 한다.
5. PyPI 절차를 설명하는 문서와 테스트가 여러 곳에 있다.
   - `docs/PUBLISHING.md:1-151@e764c7a` 전체
   - `docs/TODO.md:363-376@e764c7a` "Release And Publishing Operations"
   - `README.md:46-49,371@e764c7a`
   - `publish.sh:16,128-135@e764c7a`
   - `docs/DECISIONS.md`의 2026-06-29 Trusted Publishing 항목(203-222행), 2026-06-24 onboarding 항목의 PyPI 부분(269-292행), 2026-10-28 항목의 PyPI 배포 부분(689-697행), 2026-11-03 항목의 근거(802행)
   - `tests/test_release_automation_contract.py:9-50@e764c7a`는 `prepare-release` 이름, `--draft`, PUBLISHING.md의 "Approve the `pypi` environment deployment" 문구를 검사한다.
6. `publish.sh`는 `docs/PUBLISHING.md`에서 세 패턴을 각각 처음 한 번만 바꾼다. `` `version`: `X` ``, `./publish.sh -v X`, 그리고 첫 `vX.Y.Z`. `publish.sh:92,102-106@e764c7a`. 새 PUBLISHING.md에 구체적인 태그가 두 번 이상 나오면 두 번째부터는 다음 버전 올림 때 옛 값으로 남는다.

확인 방법: 위 파일을 `e764c7a` 기준으로 직접 읽었다. vault-builder 쪽은 로컬 checkout `vault-builder/`에서 git 주소를 검색해 확인했다. 저장소 전체에서 `PyPI|pypi|prepare-release|publish-pypi|publish-testpypi`를 검색해 위 목록 밖의 현재 문서(과거 spec, `docs/design/**`, `docs/superpowers/**`, `docs/PATCH_LOG.md` 제외)에 남은 곳이 없음을 확인했다.
## 2. Intent

사용자는 PyPI가 더 이상 필요 없는지 두 번 물었고, vault-graph가 아직 공개 배포 전이므로 배포 절차를 크게 바꿔도 된다고 했다. 그리고 새 배포 workflow를 추천하고 v0.3.0 배포까지 진행하라고 했다(brief "Person's words" 1-3).

이 변경 뒤에 다음이 성립해야 한다.

1. 배포 경로는 git 태그와 GitHub Release 하나다. PyPI와 TestPyPI는 배포 절차에 없다. [가정] 사용자의 질문과 진행 지시를 PyPI 제거 승인으로 해석했다(brief 가정1).
2. 버전을 정한 사람이 workflow 하나를 실행하면 검사, 태그, Release가 한 번에 끝난다. 중간에 draft 검토나 environment 승인을 거치지 않는다. [가정]
3. 태그가 붙은 커밋은 설치에 쓰이는 wheel이 빌드되고 검사를 통과한 커밋이다.
4. v0.3.0이 이 절차로 배포된다.
## 3. Non-goals

1. PyPI 프로젝트 `vault-graph`(0.2.1 공개)를 yank, 삭제, 유지 중 무엇으로 할지는 사람이 정한다. 되돌릴 수 없는 외부 작업이다.
2. GitHub environment `pypi`, `testpypi`와 PyPI/TestPyPI Trusted Publisher 삭제는 사람이 저장소와 계정 설정에서 한다.
3. vault-builder가 `main` 대신 태그를 설치하게 바꾸지 않는다. 다른 저장소다. README의 기본 설치 명령도 vault-builder와 같게 ref 없는 주소로 둔다.
4. 기존 태그 `v0.2.0`, `v0.2.1`과 그 Release, 첨부 파일은 건드리지 않는다.
5. `ci.yml`은 바꾸지 않는다. 9절 질문2에서 다르게 정하면 범위가 바뀐다.
6. 루트 `pyproject.toml`, 모듈 번들 방식, `tests/verify_release_dist.py`, `tests/verify_graph_module_wheels.py`, `.github/release.yml`은 바꾸지 않는다.
7. 과거 spec(`docs/specs/**` 중 이 spec 밖), `docs/design/**`, `docs/superpowers/**`, `docs/PATCH_LOG.md`는 고치지 않는다. 과거 DECISIONS 항목도 본문은 그대로 두고, 새 항목이 무엇을 대체하는지 적는다.
8. `publish.sh`의 브랜치 이름(`codex/release-v<VERSION>`)과 버전 올림 대상 파일은 바꾸지 않는다.
9. 이 PR 병합은 사람이 한다.
## 4. Design

핵심 계약: 배포 하나는 태그 `vX.Y.Z` 하나와 그 태그의 published GitHub Release 하나다. 둘 다 수동 workflow `release`만 만든다. `release`는 모든 검사가 통과한 뒤에만 태그와 Release를 만들고, 검사가 하나라도 실패하면 아무것도 만들지 않는다. Release에는 첨부 파일이 없다. 설치는 `git+https://github.com/cutehackers/vault-graph.git`(main) 또는 `...@vX.Y.Z`(태그)로 한다.

### 4.1 `.github/workflows/release.yml` (신규, `prepare-release.yml` 대체)

1. `name: release`, 트리거는 `workflow_dispatch`만 둔다. 입력은 `prepare-release.yml:5-19@e764c7a`와 같다. `version`(필수, v 없음), `target_ref`(필수, 기본 `main`), `release_notes`(선택, 비면 자동 생성 노트).
2. `permissions: contents: write`. `id-token`은 없다. `concurrency.group`은 `release-${{ inputs.version }}`, `cancel-in-progress: false`.
3. 작업 하나(`release`), `if: github.repository == 'cutehackers/vault-graph'`. 단계 순서:
   1. `actions/checkout@v4`로 `target_ref`를 `fetch-depth: 0`으로 받는다. `astral-sh/setup-uv@v6`.
   2. 버전 검사: `prepare-release.yml:38-62@e764c7a`와 같다. 입력 형식이 `^[0-9]+\.[0-9]+\.[0-9]+$`인지도 확인한다.
   3. 태그 미사용 검사: 원격에 `refs/tags/v<version>`이 있으면 실패한다. 로컬 checkout의 태그가 아니라 `git ls-remote --tags origin`으로 원격을 직접 확인한다.
   4. (9절 질문1 옵션1일 때만) 대상 커밋이 `origin/main`의 조상인지 확인하고, 아니면 실패한다.
   5. Lint, Type check, Test, `verify_graph_module_wheels.py`: `prepare-release.yml:72-79@e764c7a`의 명령을 그대로 쓴다.
   6. `rm -rf dist` 후 `uv build`, 이어서 `python tests/verify_release_dist.py dist`. `twine check`는 뺀다(결정4).
   7. `release_notes`가 있으면 `release-notes.md`에 쓴다.
   8. `gh release create "v<version>" --target "$(git rev-parse HEAD)" --title "v<version>"`에 `--notes-file release-notes.md` 또는 `--generate-notes`를 붙인다. `--draft`와 `dist/*` 인자는 없다. 이 명령이 GitHub에서 태그와 published Release를 함께 만든다.
4. 태그 push 트리거는 만들지 않는다. 사람이 직접 push한 태그에는 Release가 생기지 않는다.

### 4.2 삭제

`.github/workflows/prepare-release.yml`, `.github/workflows/publish-pypi.yml`, `.github/workflows/publish-testpypi.yml`을 지운다.

### 4.3 `publish.sh`

1. 사용법 문구 16행을 "이 스크립트는 태그도 GitHub Release도 만들지 않는다"는 뜻의 영어 문장으로 바꾼다. PyPI 언급을 없앤다.
2. `docs/PUBLISHING.md` 치환(102-106행): 세 번째 치환을 `count=1`에서 전체 치환으로 바꾼다. 그래서 PUBLISHING.md 안의 구체적인 태그 `vX.Y.Z`(숫자) 전부가 새 버전이 된다. 다른 두 치환은 그대로 둔다.
3. 마지막 안내(128-135행)를 두 단계로 바꾼다. (1) `release` workflow를 `version <VERSION>`으로 실행한다. (2) `uv tool install --force --python 3.12 git+https://github.com/cutehackers/vault-graph.git@v<VERSION>` 후 `vg --help`로 확인한다.

### 4.4 `docs/PUBLISHING.md` (전체 재작성)

절 구성:

1. `# Publishing` 다음 바로 `## Release Quick Flow`. 단계: `./publish.sh -v <version>`로 버전 올림 PR → 병합 → GitHub Actions에서 `release`를 수동 실행(`` `version`: `<version>` ``, `target_ref`: `main`, `release_notes`: "leave empty for generated notes") → Release `v<version>`과 태그 확인 → 태그 설치 확인 명령(`uv tool install --force --python 3.12 git+https://github.com/cutehackers/vault-graph.git@v<version>`, `vg --help`, `vg setup --help`, `vg ask --help`).
2. `## Safety Model`: PR과 main push는 검사만 한다. 태그와 Release는 `release` workflow만 만든다. 검사가 모두 통과해야 태그가 생긴다. 같은 태그가 있으면 멈춘다. API 토큰이나 secret을 쓰지 않는다.
3. `## Install Channels`: ref 없는 git 주소는 `main`을 설치하고 vault-builder가 이 방식을 쓴다. `@vX.Y.Z`는 배포 버전을 설치한다. PyPI의 `vault-graph`는 0.2.1에서 멈췄고 더 갱신하지 않는다.
4. `## What The Release Builds`: Release에는 첨부 파일이 없다. 그래도 `release`는 `uv build`와 `verify_release_dist.py`로 wheel을 검사한다. git 설치가 같은 소스에서 같은 wheel을 빌드하기 때문이다. 모듈 5개 번들 설명(현재 45-54행)은 PyPI 문구만 빼고 유지한다.
5. `## Required GitHub Settings`: `main` 보호, 병합 전 CI 필수, Actions 기본 권한 read-only 유지. `release`를 실행할 수 있는 사람은 저장소 write 권한자다.
6. `## Release Verification`: 로컬 검사 명령(현재 100-110행)에서 `twine check` 줄을 뺀다.
7. `## Non-Goals`: plain push나 태그 push로 배포하지 않는다. 로컬에서 태그를 push하지 않는다. Release에 파일을 첨부하지 않는다. PyPI와 TestPyPI에 올리지 않는다. 배포 중 Vault 내용을 만들거나 바꾸지 않는다.

PUBLISHING.md 전체에서 숫자로 된 태그는 현재 버전 하나만 쓴다. 다른 버전을 가리킬 때는 `vX.Y.Z`로 쓴다(4.3-2 치환 때문).

### 4.5 `README.md`

1. 46-49행: PyPI 문장을 지우고, 설치 명령이 공개 GitHub 저장소의 `main`을 HTTPS로 설치한다는 문장과 특정 배포 버전은 `@vX.Y.Z`를 붙여 설치한다는 문장으로 바꾼다. PyPI 패키지는 갱신하지 않으니 쓰지 말라는 한 문장을 남긴다(결정6).
2. "Install `vg` only"(58-61행) 명령은 그대로 두고, 그 아래에 태그 설치 예시 한 줄을 `vX.Y.Z` 형태로 덧붙인다.
3. 371행: PUBLISHING.md 설명을 "git 태그와 GitHub Release 배포 절차와 권한"으로 바꾼다.

### 4.6 `docs/TODO.md:363-376`

"Release And Publishing Operations"를 새 방향으로 바꾼다. PR과 push는 검사만, 태그와 Release는 수동 `release` workflow만, 검사 통과 전에는 태그 없음, Release 첨부 파일 없음, PyPI/TestPyPI 없음. 사람이 할 일로 PyPI 프로젝트 처리와 `pypi`/`testpypi` environment, Trusted Publisher 삭제를 적는다.

### 4.7 `docs/DECISIONS.md`

파일 끝에 `## 2026-11-05 - Release With Git Tags And GitHub Releases Only` 항목을 Question/Decision/Reason/Implications 형식으로 추가한다. 내용:

1. Decision: PyPI와 TestPyPI 배포를 없앤다. `release` workflow가 검사 후 태그와 published Release를 만든다. 첨부 파일은 없다.
2. Reason: 설치 경로(vault-builder, README)가 모두 git이고, PyPI 0.2.1은 설치 명령에 필요한 명령이 없다.
3. Implications: 대체하는 항목을 적는다. 2026-06-29 Trusted Publishing 항목 전체, 2026-06-24 onboarding 항목의 PyPI 관련 함의, 2026-10-28 항목 중 PyPI 업로드 부분(번들 방식은 유지), 2026-11-03 항목의 근거 중 "publish-pypi.yml, publish-testpypi.yml에서 다시 검사" 부분(이제 `release.yml`에서 검사). 2026-06-29 MIT 라이선스 결정은 그대로다.

### 4.8 `tests/test_release_automation_contract.py`

1. `test_prepare_release_workflow_creates_draft_release_only`를 `release.yml` 검사로 바꾼다. 확인 내용: `name == "release"`, 트리거가 `workflow_dispatch`뿐, 입력이 `version`, `target_ref`, `release_notes`, `permissions == {"contents": "write"}`, 본문에 `gh release create`, `--generate-notes`, `release-notes.md`, `git ls-remote`, `verify_release_dist.py`, `verify_graph_module_wheels.py`가 있음. `--draft`, `dist/*`, `uv publish`, `trusted-publishing`, `id-token`, `twine`이 없음.
2. 새 테스트: `prepare-release.yml`, `publish-pypi.yml`, `publish-testpypi.yml`이 없고, `.github/workflows/` 안 어느 파일에도 `pypi`(대소문자 무시)가 없다.
3. `test_publishing_doc_starts_with_release_quick_flow` 수정: "run `prepare-release` manually"와 "Publish the draft GitHub Release", "Approve the `pypi` environment deployment" 검사를 빼고, "In GitHub Actions, run `release` manually"와 `git+https://github.com/cutehackers/vault-graph.git@v{version}`이 앞 1000자 안에 있는지 검사한다.
4. 새 테스트: PUBLISHING.md 안의 숫자 태그(`v[0-9]+\.[0-9]+\.[0-9]+`)는 모두 `v{version}`이다.
5. 새 테스트: `publish.sh`에 `pypi`(대소문자 무시)와 `prepare-release`가 없고 `release` workflow 안내가 있다.
6. `test_github_generated_release_notes_are_categorized`는 그대로 둔다.

### 4.9 v0.3.0 배포 (PR 병합 후)

버전 파일은 이미 0.3.0이므로 `publish.sh`는 실행하지 않는다. 병합 후 `release`를 `version: 0.3.0`, `target_ref: main`, `release_notes` 비움으로 실행한다. 태그 `v0.3.0`은 이 PR의 병합 커밋을 가리킨다.
## 5. Decisions

표기: [사용자] 사용자가 대화에서 정한 방향(spec gate에서 최종 확인), [가정] 작성자가 정한 내용.

1. 결정1 [사용자] PyPI와 TestPyPI 배포를 없애고 git 태그와 GitHub Release만 배포 경로로 쓴다. `publish-pypi.yml`, `publish-testpypi.yml`을 지운다. 이유: 모든 설치 경로가 git이고, 사용자가 PyPI가 필요 없는지 두 번 묻고 재설계를 지시했다. 사용자의 명시적 "제거" 문장은 없으므로 gate에서 확인한다.
2. 결정2 [가정] `release`는 draft 없이 바로 published Release를 만든다. 이유: draft는 PyPI 업로드 전에 사람이 첨부 파일을 보려고 있던 단계다. 버전과 ref는 workflow를 실행하는 사람이 이미 정한다.
3. 결정3 [가정] Release에 `dist/*`를 첨부하지 않는다. 이유: 설치는 git 주소로 하고, 첨부 wheel을 쓰는 경로가 없다. 첨부하면 내려받는 사람이 그 wheel을 지원 설치 방법으로 오해할 수 있다.
4. 결정4 [가정] wheel 빌드와 `verify_release_dist.py`, `verify_graph_module_wheels.py`는 유지하고 `twine check`는 뺀다. 이유: git 설치가 같은 wheel을 빌드하므로 앞의 둘은 여전히 의미가 있다. `twine check`는 PyPI 업로드용 메타데이터(README 렌더링) 검사라서 업로드가 없으면 할 일이 없다.
5. 결정5 [가정] 새 파일 이름은 `release.yml`, workflow 이름은 `release`다. 입력 세 개는 `prepare-release`와 같다. 이유: 단계가 하나뿐이므로 "prepare"가 맞지 않고, 입력을 유지하면 사용법이 그대로다.
6. 결정6 [가정] README 기본 설치 명령은 ref 없는 주소로 두고 태그 설치 예시를 덧붙이며, PyPI는 쓰지 말라고 적는다. 이유: vault-builder와 같은 명령을 보여 줘야 하고, PyPI 0.2.1을 설치하면 설치 명령이 쓰는 명령이 없다.
7. 결정7 [가정] 태그 미사용 검사는 `git ls-remote`로 원격을 직접 본다. 이유: checkout이 태그를 모두 받아 오는지에 기대지 않는다(7절 1번).
8. 결정8 [가정] `publish.sh`의 PUBLISHING.md 태그 치환을 전체 치환으로 바꾸고, PUBLISHING.md에는 숫자 태그를 현재 버전 하나만 쓴다. 이유: 새 Quick Flow에는 Release 이름과 설치 명령 두 곳에 태그가 나온다. `count=1`이면 두 번째가 옛 버전으로 남는다. 계약 테스트(4.8-4)가 이를 막는다.
9. 결정9 [가정] 과거 DECISIONS 항목은 고치지 않고 새 항목이 대체 범위를 적는다. 이유: DECISIONS 작성 규칙(`docs/DECISIONS.md:6-18@e764c7a`)이 결정 기록을 이력으로 쌓는다.
10. 결정10 [가정] `publish.sh`는 남기고 문구와 안내만 고친다. 이유: 버전 파일 5개와 `uv.lock`을 함께 바꾸는 PR 절차는 PyPI와 상관없이 필요하다.
## 6. Failure and boundary behavior

| 상황 | 기대 동작 |
|---|---|
| `version` 입력이 `pyproject.toml` 또는 `__version__`과 다름, 또는 `X.Y.Z` 형식이 아님 | 버전 검사 단계에서 실패한다. 태그와 Release는 생기지 않는다. |
| 원격에 `v<version>` 태그가 이미 있음(재실행 포함) | 태그 미사용 검사에서 "already exists"로 실패한다. 기존 태그와 Release는 바뀌지 않는다. |
| lint, mypy, test, 모듈 wheel 검사, `uv build`, `verify_release_dist.py` 중 하나가 실패 | 그 단계에서 멈춘다. 태그와 Release는 생기지 않는다. |
| 검사 뒤, 생성 전에 다른 곳에서 같은 태그가 생김 | `gh release create`가 실패한다. 이미 있는 태그를 옮기지 않는다. |
| 같은 버전으로 두 번 동시에 실행 | concurrency group이 두 번째를 대기시키고, 두 번째는 태그 미사용 검사에서 실패한다. |
| `target_ref`가 없는 브랜치나 커밋 | checkout 단계에서 실패한다. |
| `target_ref`가 `main`에 병합되지 않은 커밋 | 질문1 옵션1이면 조상 검사에서 실패한다. 옵션2이면 그 커밋에 태그가 붙는다(지금 `prepare-release`와 같다). |
| `release_notes`가 여러 줄이거나 따옴표를 포함 | 환경 변수로 넘겨 파일에 쓰므로 그대로 Release 본문이 된다. |
| fork에서 실행 | 저장소 조건으로 작업이 건너뛰어진다. |
| 사람이 로컬에서 태그를 직접 push | workflow가 돌지 않고 Release도 생기지 않는다. PUBLISHING.md Non-Goals가 이를 금지한다. |
| 사용자가 ref 없는 git 주소로 설치 | 지금과 같이 `main`이 설치된다. |
| 사용자가 `@v0.3.0`으로 설치 | 태그 커밋의 소스에서 wheel을 빌드해 설치한다. |
| 사용자가 PyPI에서 `uv tool install vault-graph` | 0.2.1이 설치된다. 이 변경으로 막지 않는다. README가 쓰지 말라고 안내한다. |
| `publish.sh -v 0.3.1` 실행 | PUBLISHING.md의 `version` 값, `./publish.sh -v`, 모든 숫자 태그가 0.3.1로 바뀐다. 마지막 안내가 `release` workflow와 태그 설치 명령을 보여 준다. |
## 7. What could be wrong

1. `actions/checkout`이 `fetch-depth: 0`일 때 원격 태그를 모두 받아 오는지 이 세션에서 문서로 확인하지 않았다. 결정7이 `git ls-remote`를 쓰는 이유다.
2. `gh release create`에 없는 태그와 `--target <sha>`를 주면 GitHub가 그 커밋에 태그를 만들고 Release와 함께 생성한다고 보았다. 이 세션에서 `gh` 문서로 다시 확인하지 않았다. 지금 `prepare-release.yml:95-110@e764c7a`도 같은 방식이고 `v0.2.0`, `v0.2.1` Release가 이 방식으로 만들어졌다(2026-10-28 spec 7절 7번 기록).
3. 저장소에 태그 생성을 제한하는 ruleset이 있는지 확인하지 않았다. 있으면 `GITHUB_TOKEN`의 태그 생성이 거부되어 생성 단계에서 실패한다.
4. 자동 생성 노트는 이전 태그(`v0.2.1`로 예상)부터의 PR을 모은다고 보았다. 이전 태그로 무엇이 잡히는지는 실행 전에 확인하지 않았다.
5. `uv tool install git+...`가 만드는 wheel과 `uv build`가 만드는 wheel이 같다고 보았다. `uv build`는 sdist를 거쳐 wheel을 만들고, git 설치는 소스 트리에서 바로 만들 수 있다. 2026-10-28 spec의 A-4가 sdist 재빌드 wheel과 직접 빌드 wheel이 같음을 검사했으므로 차이는 작을 것으로 본다.
6. 대상 커밋이 `main`에 있는지 검사하지 않으면(질문1 옵션2), 병합되지 않은 브랜치 커밋에 공개 태그가 붙을 수 있다.
7. 모듈이 `vault-graph` 의존성을 새로 import하거나 rustworkx 최소 버전에서 깨지는 문제는 PR CI에서 보이지 않고 `release` 실행 때 처음 드러난다(`docs/DECISIONS.md:804@e764c7a`). vault-builder가 `main`을 설치하므로, 그 사이 설치한 사용자는 검사되지 않은 커밋을 받는다. 이 위험은 이 변경 전에도 있었다. 질문2가 다룬다.
8. PyPI 0.2.1 문서를 보고 `uv tool install vault-graph`를 실행하는 사용자가 있는지 확인하지 않았다.
## 8. Acceptance criteria

명령은 모두 저장소 루트에서 Python 3.12로 실행한다.

- A-1 `.github/workflows/`에 `ci.yml`과 `release.yml`만 있다. `prepare-release.yml`, `publish-pypi.yml`, `publish-testpypi.yml`이 없다. 어느 workflow 파일에도 `pypi`(대소문자 무시), `uv publish`, `trusted-publishing`, `id-token`이 없다.
- A-2 `release.yml`은 4.1을 따른다. `name`이 `release`, 트리거가 `workflow_dispatch`뿐, 입력이 `version`, `target_ref`(기본 `main`), `release_notes`(기본 빈 값), 권한이 `contents: write`뿐이다. `gh release create`에 `--draft`도 `dist/*`도 없다. 태그 미사용 검사는 `git ls-remote`를 쓴다.
- A-3 `release.yml`에서 버전 검사, 태그 미사용 검사, (질문1 옵션1이면) 조상 검사, Lint, Type check, Test, `verify_graph_module_wheels.py`, `uv build`, `verify_release_dist.py dist` 단계가 모두 `gh release create` 단계보다 앞에 있다. `twine`이 없다.
- A-4 `tests/test_release_automation_contract.py`가 4.8의 검사를 모두 담고, `uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests`가 성공한다. `ci.yml`의 Lint, Type check 명령(`ci.yml:18-21@e764c7a`)도 성공한다.
- A-5 `publish.sh`에 `pypi`(대소문자 무시)와 `prepare-release`가 없다. 마지막 안내에 `release` workflow와 `git+https://github.com/cutehackers/vault-graph.git@v${VERSION}` 설치 명령이 있다. 브랜치 이름 `codex/release-v${VERSION}`과 버전 올림 대상 파일 목록(`publish.sh:84-93,111-117@e764c7a`)은 바뀌지 않는다.
- A-6 `publish.sh`의 PUBLISHING.md 치환 코드를 임시 사본에 버전 `9.9.9`로 실행하면, 결과 문서의 숫자 태그가 모두 `v9.9.9`이고 `` `version`: `9.9.9` ``와 `./publish.sh -v 9.9.9`가 있다. 이 확인은 PR 설명에 실행 결과로 남긴다.
- A-7 `docs/PUBLISHING.md`가 `# Publishing\n\n## Release Quick Flow\n\n`로 시작하고 4.4의 절을 담는다. "Approve the `pypi`", "Trusted Publisher", "TestPyPI Flow", "PyPI Flow" 문구가 없다. 숫자 태그는 현재 버전 하나뿐이다.
- A-8 `README.md`에 "has releases on PyPI" 문장이 없고, 태그 설치 예시(`@vX.Y.Z`)와 PyPI를 쓰지 말라는 안내가 있다. 기본 설치 명령 `uv tool install --python 3.12 git+https://github.com/cutehackers/vault-graph.git`은 그대로다. More Documentation의 PUBLISHING.md 설명에 "PyPI"가 없다.
- A-9 `docs/TODO.md` "Release And Publishing Operations"에 PyPI 업로드 방향이 없고 4.6의 내용과 사람이 할 일이 있다.
- A-10 `docs/DECISIONS.md` 끝에 2026-11-05 항목이 Question/Decision/Reason/Implications 형식으로 있고, 4.7-3의 대체 항목 네 개를 날짜와 제목으로 가리킨다. 기존 항목 본문은 바뀌지 않는다(`git diff main -- docs/DECISIONS.md`에 삭제 줄이 없다).
- A-11 범위 제한: `git diff --stat main`에 나오는 파일은 `.github/workflows/release.yml`, 삭제된 workflow 3개, `publish.sh`, `docs/PUBLISHING.md`, `README.md`, `docs/TODO.md`, `docs/DECISIONS.md`, `tests/test_release_automation_contract.py`, 그리고 이 spec 디렉터리뿐이다. `src/**`, `packages/**`, `pyproject.toml`, `uv.lock`, `ci.yml`(질문2 옵션1일 때)은 바뀌지 않는다.
- A-12 병합 후 v0.3.0 배포(수동): `release`를 `version: 0.3.0`, `target_ref: main`, `release_notes` 비움으로 실행하면 성공한다. 태그 `v0.3.0`이 그 시점 `main` 커밋을 가리키고, Release `v0.3.0`이 draft가 아니며 첨부 파일이 없다. `uv tool install --force --python 3.12 git+https://github.com/cutehackers/vault-graph.git@v0.3.0` 후 `vg --help`, `vg setup --help`, `vg ask --help`, `vg mcp unregister --help`가 성공한다.
- A-13 A-12 직후 같은 입력으로 `release`를 다시 실행하면 태그 미사용 검사에서 실패하고, 태그 `v0.3.0`과 Release는 바뀌지 않는다.
## 9. Open decisions

2026-11-05 spec gate 답변: 사용자가 spec(결정1 PyPI 제거와 결정2~10 포함)을 승인했다. 질문1은 옵션1(`main`에 있는 커밋만 배포)을 골랐다. 질문2는 옵션1(`ci.yml` 유지)을 골랐고, vault-builder가 태그를 설치하도록 바꾸는 일은 v0.3.0 배포 후 별도 작업으로 한다.

### 질문1 `release`가 `main`에 병합되지 않은 커밋에도 태그를 붙이게 둘 것인가

- 배경: 지금 `prepare-release`는 `target_ref`로 아무 브랜치나 커밋을 받는다(`prepare-release.yml:10-14@e764c7a`). PyPI가 있을 때는 draft 검토와 `pypi` 승인이 마지막 확인이었는데, 새 `release`는 실행하면 바로 공개 태그를 만든다.
- 옵션1 대상 커밋이 `origin/main`의 조상이 아니면 실패시킨다(4.1-3-4 단계 추가). 잃는 것: 병합 전 브랜치에서 급한 수정 배포를 바로 할 수 없고, 먼저 `main`에 병합해야 한다.
- 옵션2 지금처럼 검사하지 않는다. 잃는 것: 입력 실수로 리뷰되지 않은 커밋에 공개 태그가 붙을 수 있다.
- 추천: 옵션1. 사람의 확인 단계가 하나 줄었으므로 그 자리를 검사 하나로 채운다. 사용자 혼자 배포하는 지금 단계에서 병합 전 배포가 필요한 경우는 드물다.
- 답이 바꾸는 것: 4.1-3-4 단계, A-3, 6절 해당 행.
- 답: 옵션1 (사용자, 2026-11-05).

### 질문2 PR CI에 wheel 빌드 검사를 다시 넣을 것인가

- 배경: 2026-11-03에 PR CI를 ruff, mypy, pytest로 줄였다(`docs/DECISIONS.md:796-804@e764c7a`). wheel 빌드와 모듈 wheel 검사는 배포 workflow에서만 돈다. vault-builder는 태그가 아니라 `main`을 설치하므로, 배포 전 `main`에서 wheel이 깨지면 그 사이 설치한 사용자가 깨진 버전을 받는다. 이 상황은 이 변경 전에도 같았다.
- 옵션1 `ci.yml`을 바꾸지 않는다. wheel 검사는 `release`에서만 돈다. 잃는 것: `main`의 wheel 문제가 다음 배포 때까지 드러나지 않을 수 있다.
- 옵션2 `ci.yml` `verify` 작업에 `uv build`와 `verify_release_dist.py dist`만 추가한다(모듈 wheel 검사는 넣지 않는다). 잃는 것: PR마다 빌드 시간이 조금 늘고, 2026-11-03 결정을 일부 되돌리는 새 DECISIONS 문장이 필요하다.
- 추천: 옵션1. 사용자가 PR CI를 줄이기로 정한 지 이틀이고, 이번 변경은 배포 경로만 다룬다. `main` 설치 위험은 vault-builder가 태그를 설치하게 바꾸는 쪽(3절 3번)이 더 직접적인 해결이다.
- 답이 바꾸는 것: 옵션2이면 `ci.yml`이 범위에 들어오고(3절 5번, A-11), DECISIONS 새 항목에 2026-11-03 결정 변경을 적는다.
- 답: 옵션1 (사용자, 2026-11-05). 후속: vault-builder `_install_vg`(`vault-builder/tools/vault_migration/onboarding.py:583-586`)가 태그를 설치하게 바꾼다.
