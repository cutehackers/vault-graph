# Spec: 단일 패키지 배포로 전환

- spec id: 2026-10-28-single-package-release
- task: 20261028-v0-2-0-pypi-00ba
- base: main @ 2bc19ca, branch feat/jh/single-package-release

## 1. Problem

v0.2.0 배포가 PyPI에 아무것도 올리지 못했다.

1. GitHub Actions `publish-pypi` 실행 40661532945가 첫 업로드 파일 `nolemy_graph_document-0.1.0-py3-none-any.whl`에서 PyPI 400 오류로 멈췄다. 요지는 Trusted Publishing(OIDC) 신원으로는 PyPI에 아직 없는 프로젝트를 새로 만들 수 없다는 것이다. 근거는 brief에 기록된 실행 로그 요약이며, 이 spec 작성 중 로그를 직접 다시 열어 보지는 않았다.
2. 원인은 루트 배포 `vault-graph`가 모듈 5개를 별도 PyPI 배포로 요구하는 구조다.
   - 루트 `[project].dependencies`가 `nolemy-*` 5개를 `==0.1.0`으로 요구한다. `pyproject.toml:22-39@2bc19ca`
   - 루트 wheel에는 `src/vault_graph`만 들어간다. `pyproject.toml:58-59@2bc19ca`
   - `publish-pypi`와 `publish-testpypi`는 `uv build --all-packages`로 6개를 빌드하고 `dist/nolemy_*`를 먼저 올린 뒤 `dist/vault_graph-*`를 올린다. `.github/workflows/publish-pypi.yml:34-45@2bc19ca`, `.github/workflows/publish-testpypi.yml:32-45@2bc19ca`
   - `prepare-release`도 `uv build --all-packages` 결과 `dist/*` 전체를 draft Release에 첨부한다. `.github/workflows/prepare-release.yml:80-111@2bc19ca`
   - PyPI Trusted Publisher 등록 안내는 `vault-graph` 하나만 다룬다. `docs/PUBLISHING.md:60-80@2bc19ca`
3. `nolemy-*`가 PyPI에 없으므로, 모듈 업로드 단계를 지우는 것만으로는 해결되지 않는다. 그 상태로 `vault-graph 0.2.0`을 올리면 사용자의 `uv tool install vault-graph`가 의존성 해석에서 실패한다.
4. 0.1.4까지는 `vault-graph` 하나만 배포해서 성공했다(brief 기록).

확인 방법: 위 파일을 `2bc19ca` 기준으로 직접 읽었다. 모듈별 런타임 의존성은 `packages/*/pyproject.toml@2bc19ca`에서 확인했다. 저장소 전체에서 `nolemy`를 검색해 `src/vault_graph`가 배포 이름 `nolemy-*`를 런타임에 조회하지 않는다는 것도 확인했다. 배포 이름을 조회하는 곳은 `tests/benchmarks/measure_document_graph_backend.py:195-196@2bc19ca`와 `tests/benchmarks/measure_evidence_linking.py:189-190@2bc19ca`뿐이다.

## 2. Intent

사용자는 모듈 5개를 아직 PyPI에 별도 패키지로 배포하고 싶지 않다. 개별 배포에는 프로젝트마다 별도의 배포 준비가 필요하기 때문이다. 대신 다음 두 가지가 동시에 성립하기를 원한다.

1. 개발할 때는 모듈 5개를 지금처럼 서로 분리된 모듈로 엄격하게 관리한다.
2. 배포할 때는 0.1.4까지처럼 `vault-graph` 하나만 PyPI에 올리고, 사용자는 그 하나로 모든 기능을 설치한다.

[가정] 나중에 독립 배포를 다시 켤 때 모듈 pyproject와 배포 이름을 그대로 쓸 수 있는 상태를 원한다.

## 3. Non-goals

1. 모듈 5개를 PyPI나 TestPyPI에 배포하지 않는다. 모듈용 Trusted Publisher 등록도 하지 않는다.
2. 모듈의 배포 이름(`nolemy-*`), 버전(0.1.0), `packages/*/pyproject.toml` 내용은 바꾸지 않는다. [가정]
3. 최상위 import 이름(`graph_search`, `graph_document`, `text_embeddings`, `vector_search`, `vector_index`)은 바꾸지 않는다. 이 이름이 다른 배포와 충돌할 수 있는 위험(위험1)은 이번 범위 밖이며 7절에 남긴다. [가정]
4. 모듈 코드, `vault_graph` 코드, 공개 API는 바꾸지 않는다.
5. `publish.sh`, 배포 승인 방식(GitHub Actions, Trusted Publishing, `pypi` environment 승인)은 바꾸지 않는다.
6. `README.md`의 모듈 소개 문단(`README.md:215-220@2bc19ca`)과 과거 설계 문서(`docs/design/**`)는 고치지 않는다. 설치 명령을 안내하지 않으므로 이번 배포 실패와 관계없다.
7. benchmark 스크립트의 `importlib.metadata.version("nolemy-*")` 호출은 고치지 않는다. 개발 환경에서는 모듈이 계속 설치되므로 동작한다.

## 4. Design

핵심 계약: PyPI에 올라가는 배포는 `vault-graph` 하나다. 이 wheel은 `vault_graph`와 모듈 5개의 import 패키지를 모두 포함하고, `Requires-Dist`에는 `nolemy-*`가 없고 모듈이 쓰는 외부 의존성이 직접 들어간다. 모듈 5개는 저장소 안에서는 지금처럼 독립 프로젝트(각자 pyproject, CI 검사, 독립 wheel smoke)로 남지만, 그 wheel은 검사용으로만 빌드하고 배포하지 않는다.

### 4.1 루트 `pyproject.toml` (`pyproject.toml:22-69@2bc19ca`)

1. `[project].dependencies`
   - `nolemy-*` 5개 줄(28-32행)을 제거한다.
   - 모듈 런타임 외부 의존성을 직접 선언한다. `rustworkx>=0.17,<0.18`(27행, 이미 있음), `fastembed>=0.8,<1`(text-embeddings `fastembed` extra), `chromadb>=1.5.9,<2`(vector-search `chroma` extra)를 추가한다.
2. `[dependency-groups].dev`에 `nolemy-*` 5개를 추가한다. `[tool.uv.workspace].members`와 `[tool.uv.sources]`의 `workspace = true`는 유지한다. 그러면 `uv sync`가 개발 환경에 모듈을 editable로 설치하고, 이 의존은 wheel 메타데이터에 들어가지 않는다.
3. `[tool.hatch.build.targets.wheel].packages`에 다음 5개 경로를 추가한다. `packages/graph-search/src/graph_search`, `packages/graph-document/src/graph_document`, `packages/text-embeddings/src/text_embeddings`, `packages/vector-search/src/vector_search`, `packages/vector-index/src/vector_index`. wheel 안에서는 각각 최상위 `graph_search/` 등으로 들어간다.
4. sdist는 hatch 기본 규칙(저장소의 무시되지 않은 파일 전체 포함)을 그대로 쓴다. 따라서 `packages/*/src`가 sdist에 들어가고, sdist에서 같은 wheel을 다시 빌드할 수 있어야 한다. 이 성질은 A-4로 검사한다.
5. `uv.lock`을 다시 생성한다.

### 4.2 배포 산출물 검사 스크립트 (신규)

`tests/verify_release_dist.py`를 추가한다. 시그니처: `def main(dist_dir: Path) -> None`, 명령행은 `python tests/verify_release_dist.py dist`.
검사 내용:

1. `dist/` 안의 파일이 정확히 `vault_graph-<version>-*.whl` 1개와 `vault_graph-<version>.tar.gz` 1개다. `<version>`은 루트 `pyproject.toml`의 버전이다. `nolemy_*` 파일이 있으면 실패한다.
2. wheel 안에 `vault_graph/` 그리고 모듈 5개의 `<import 이름>/__init__.py`가 있다.
3. wheel `METADATA`의 `Requires-Dist`에 이름이 `nolemy-`로 시작하는 요구가 없다.
4. sdist 안에 `packages/<dir>/src/<import 이름>/__init__.py` 5개가 있다.

### 4.3 배포 workflow (`.github/**`, sensitive path)

1. `publish-pypi.yml:34-45@2bc19ca`
   - `Build distributions`를 `uv build --all-packages`에서 `uv build`(루트만)로 바꾼다.
   - `Check distributions` 뒤에 `python tests/verify_release_dist.py dist` 단계를 추가한다.
   - `Publish independent modules to PyPI` 단계(38-41행)를 삭제한다. `dist/vault_graph-*` 업로드 단계만 남긴다.
2. `publish-testpypi.yml:32-45@2bc19ca`: 위와 같은 세 가지 변경을 한다(`dist/nolemy_*` 업로드 단계 36-40행 삭제).
3. `prepare-release.yml:80-83@2bc19ca`: `uv build`(루트만)로 바꾸고 `verify_release_dist.py` 단계를 추가한다. draft Release에 첨부되는 `dist/*`는 `vault-graph` wheel과 sdist 2개가 된다.
4. `ci.yml:61-77@2bc19ca` `verify` 작업: 이미 `uv build`(루트만)이므로 `Check distributions` 뒤에 `verify_release_dist.py` 단계만 추가한다. PR 단계에서 배포 산출물 문제를 먼저 잡기 위해서다.
5. `ci.yml:13-60@2bc19ca`의 `graph-search-runtime-compatibility`, `independent-modules` 작업은 바꾸지 않는다. 모듈별 lint, mypy, test, build, twine check가 계속 돈다.
6. 기존 `Verify ...` 단계의 이름과 명령은 바꾸지 않는다.

### 4.4 `tests/verify_graph_module_wheels.py` (`340-425@2bc19ca`, `160-272@2bc19ca`)

1. 유지: 6개 wheel 빌드, 각 wheel의 이름·버전·`Requires-Dist`가 해당 pyproject와 맞는지 확인(355-372행), 모듈별 venv smoke(374-405행). 루트 wheel의 `Requires-Dist` 확인은 4.1의 새 루트 의존성 기준으로 그대로 통과해야 한다.
2. 변경: "vault" venv(406-424행)는 루트 wheel 파일 하나만 설치한다. 외부 의존성은 기본 PyPI에서 받는다. 모듈 wheel은 설치하지 않는다.
3. 추가 확인(vault venv):
   - `importlib.metadata`로 조회했을 때 이름이 `nolemy-`로 시작하는 배포가 하나도 설치되어 있지 않다.
   - 모듈 5개를 import할 수 있고, 각 모듈의 `__init__.py`가 `vault-graph` 배포의 파일 목록(`importlib.metadata.files("vault-graph")`)에 들어 있다.
   - 기존 `VAULT_SMOKE`와 `vg --help` 확인은 그대로 통과한다.
4. 삭제: `install_from_local_simple_index`(160-272행)는 루트 요구가 모듈 배포를 끌어오는 구조를 검사하던 함수이므로 지운다. 루트 wheel과 모듈 wheel을 한 venv에 함께 설치하면 같은 파일을 두 배포가 소유하게 되므로 이 조합은 더 이상 만들지 않는다.

### 4.5 의존성 일치 검사 (위험2, 신규 pytest)

`tests/test_root_dependency_alignment.py`를 추가한다. 빌드 없이 pyproject만 읽으므로 일반 `pytest` 실행에 포함된다.

1. 비교 대상 집합 = 모듈 5개 각각의 `[project].dependencies` 전체 + 루트가 예전에 켜던 extra(`text-embeddings`의 `fastembed`, `vector-search`의 `chroma`, `graph-document`의 `search`)의 의존성. 단, 이름이 `nolemy-`로 시작하는 내부 요구는 뺀다. 내부 모듈은 같은 wheel에 들어 있기 때문이다.
2. 비교 대상의 모든 요구가 루트 `[project].dependencies`에 `packaging.requirements.Requirement` 기준으로 같은 값으로 있어야 한다.
3. 루트 `[project].dependencies`에 `nolemy-`로 시작하는 요구가 없어야 한다.
4. 루트 `[dependency-groups].dev`에 `nolemy-*` 5개가 모두 있어야 한다.

### 4.6 문서

1. `docs/PUBLISHING.md`: PyPI에는 `vault-graph`만 올라가고 모듈 5개는 그 wheel 안에 포함된다는 점, 모듈 Trusted Publisher는 등록하지 않는다는 점을 적는다. `Release Verification`(84-94행)은 바꾸지 않는다.
2. `docs/ARCHITECTURE.md:132,177@2bc19ca`: "독립 배포 패키지 5개"를 "독립 모듈 5개(현재 `vault-graph` wheel에 포함해 배포)"로 고친다. 배포 이름 표(169-175행)는 유지한다.
3. `docs/DECISIONS.md`: spec 승인 후 새 항목을 Question/Decision/Reason/Implications 형식으로 추가한다. 2026-10-04 배포 이름 결정은 유지하되, PyPI 배포를 미룬다는 내용을 새 항목에 적는다.

## 5. Decisions

표기: [사용자] 사용자가 대화에서 받아들인 방향(spec gate에서 최종 확인), [가정] 작성자가 정한 내용.

1. 결정1 [사용자] 모듈 5개를 루트 wheel에 포함하고, 루트 `dependencies`에서 `nolemy-*`를 빼고 외부 의존성을 직접 선언한다. 이유: `vault-graph` Trusted Publisher 하나로 배포가 끝나고, 사용자는 0.1.4와 같은 방식으로 설치한다.
2. 결정2 [사용자] 배포 workflow는 `vault_graph-*`만 빌드하고 올리며, wheel 내용과 `Requires-Dist`를 검사한다. 이유: 모듈 wheel이 실수로 올라가거나, 루트 wheel이 PyPI에 없는 `nolemy-*`를 요구하는 상태로 올라가는 것을 업로드 전에 막는다.
3. 결정3 [사용자] `independent-modules` CI와 모듈별 독립 wheel smoke는 유지한다. 이유: 배포는 하나로 합치되 개발 중 모듈 경계는 계속 강제한다.
4. 결정4 [사용자] `nolemy-*`는 `[dependency-groups].dev`로 옮기고 workspace 설정은 유지한다. 이유: `uv sync`가 개발 환경에 모듈을 editable로 설치하고, dependency group은 wheel 메타데이터에 들어가지 않는다.
5. 결정5 [가정] 모듈 pyproject, 배포 이름, 버전 0.1.0은 그대로 둔다. 이유: 독립 배포를 다시 켤 때 그대로 쓴다. `independent-modules` 검사도 이 파일들에 의존한다.
6. 결정6 [가정] 배포 산출물 검사는 새 스크립트 `tests/verify_release_dist.py`로 하고, 이미 빌드된 `dist/`를 대상으로 한다. 이유: 실제로 업로드되는 파일을 검사해야 한다. `verify_graph_module_wheels.py`는 임시 디렉터리에 따로 빌드하므로 업로드 파일을 보지 않는다.
7. 결정7 [가정] 의존성 일치 검사(위험2)는 이번 범위에 넣고, 빌드 없는 pytest 테스트로 한다. 이유: 모듈에 의존성이 추가되었는데 루트에 빠지면, 개발 환경에서는 workspace 설치로 통과하고 배포 wheel에서만 `ImportError`가 난다. pytest에 두면 모든 CI 실행에서 빠르게 잡힌다.
8. 결정8 [가정] 루트 wheel과 모듈 wheel을 한 환경에 함께 설치하는 검사는 없앤다. 이유: 같은 파일을 두 배포가 소유하게 되어, 한쪽을 지우면 다른 쪽 파일도 사라질 수 있다. 사용자 환경에서는 이 조합이 생기지 않는다(모듈이 PyPI에 없음).
9. 결정9 [가정] `graph_document.search_bridge`는 루트 wheel에서 `graph_search`가 항상 함께 설치되므로 항상 사용 가능하다. 코드 변경은 없다. 모듈 단독 wheel smoke(`DOCUMENT_SMOKE`)가 `graph_search` 없는 경우를 계속 검사한다.
10. 결정10 [가정] sdist는 hatch 기본 포함 규칙을 쓰고 별도 `include` 설정을 추가하지 않는다. 이유: 기본 규칙이 이미 `packages/`를 포함한다. A-4가 이 가정을 검사하며, 실패하면 그때 sdist `include`를 추가한다.

## 6. Failure and boundary behavior

| 상황 | 기대 동작 |
|---|---|
| `dist/`에 `nolemy_*` 파일이 생김(빌드 명령이 `--all-packages`로 되돌아감) | `verify_release_dist.py`가 실패하고 업로드 단계에 도달하지 않는다. |
| 루트 wheel에 모듈 하나가 빠짐(hatch `packages` 누락) | `verify_release_dist.py`가 빠진 import 이름을 출력하고 실패한다. vault venv 검사에서도 import가 실패한다. |
| 루트 `Requires-Dist`에 `nolemy-*`가 남음 | `verify_release_dist.py`와 `test_root_dependency_alignment.py`가 실패한다. |
| 모듈 pyproject에 외부 의존성이 추가되었는데 루트에 없음 | `test_root_dependency_alignment.py`가 빠진 요구를 출력하고 실패한다. |
| 모듈과 루트의 같은 의존성 범위가 다름(예: `chromadb` 범위 불일치) | `test_root_dependency_alignment.py`가 실패한다. 범위를 맞추는 것은 사람이 한다. |
| sdist에 `packages/*/src`가 없음 | `verify_release_dist.py`가 실패한다. |
| 개발자가 `uv sync` 실행 | 루트와 `nolemy-*` 5개가 editable로 설치되고, 기존 `pytest`, `ruff`, `mypy` 명령이 그대로 동작한다. |
| `independent-modules` CI의 모듈 단독 실행 | 지금과 같다. 루트 변경의 영향을 받지 않는다. |
| 사용자가 PyPI에서 `uv tool install vault-graph` 실행 | wheel 하나와 외부 의존성만 설치된다. `nolemy-*`를 찾지 않는다. |
| 사용자 환경에 이미 같은 최상위 import 이름(`graph_search` 등)을 쓰는 다른 배포가 설치됨 | 이번 범위에서 막지 않는다(위험1). 파일 덮어쓰기가 일어날 수 있다. 7절 참고. |
| `uv publish` 중 PyPI에 같은 파일이 이미 있음 | 기존 `--check-url` 동작대로 건너뛴다. 변경 없음. |
| 0.2.0 재사용을 고르고 태그 `v0.2.0`이 남아 있음 | `prepare-release.yml:63-71@2bc19ca`가 "Tag already exists"로 실패한다. 9절 질문1의 절차대로 Release와 태그를 먼저 지워야 한다. |

## 7. What could be wrong

1. 위험1 최상위 import 이름 충돌. 루트 wheel이 `graph_search`, `graph_document`, `text_embeddings`, `vector_search`, `vector_index`를 site-packages 최상위에 설치한다. PyPI의 다른 배포가 같은 이름을 쓰면 서로 파일을 덮어쓴다. PyPI에 같은 import 이름을 쓰는 배포가 있는지는 확인하지 않았다. 2026-10-04 결정에서 배포 이름 `graph-search`가 이미 다른 게시자 소유였다는 기록(`docs/DECISIONS.md:20-28@2bc19ca`)이 있으므로 가능성은 있다. 이번 범위 밖이다.
2. hatch `packages`에 `packages/<dir>/src/<module>` 경로를 주면 wheel 안에 최상위 `<module>/`로 들어간다고 가정했다. 실제 빌드로 확인하지 않았다. A-3이 검사한다.
3. 개발 환경에서 루트 editable 설치와 `nolemy-*` editable 설치가 같은 소스 경로를 `sys.path`에 두 번 추가할 수 있다. 동작에는 문제가 없을 것으로 보지만 hatch editable 방식으로 실제 확인하지 않았다.
4. hatch sdist 기본 규칙이 `packages/*/src`를 포함한다고 가정했다. `.gitignore`나 hatch 기본 제외 규칙에 걸리는지 확인하지 않았다. A-4가 검사한다.
5. [확인됨 2026-10-28] 실행 40661532945 로그에서 첫 업로드 파일 `nolemy_graph_document-0.1.0-py3-none-any.whl`이 400으로 실패하고 작업이 종료된 것을 확인했다.
6. [확인됨 2026-10-28] PyPI `https://pypi.org/pypi/vault-graph/0.2.0/json`이 404를 반환한다. TestPyPI의 `vault-graph` 0.2.0과 0.2.1도 404다.
7. [확인됨 2026-10-28] 태그 `v0.2.0`과 published Release `v0.2.0`이 있다. Release에는 `nolemy_*` 10개와 `vault_graph-0.2.0` wheel, sdist가 첨부되어 있다.
8. 사용자 환경에 설치되는 외부 의존성 집합은 `2bc19ca`의 루트와 같다고 가정했다. `2bc19ca`의 루트도 `[fastembed]`, `[chroma]` extra로 `fastembed`와 `chromadb`를 이미 끌어왔기 때문이다. 0.1.4와 비교했을 때 의존성이 늘었는지는 확인하지 않았다.

## 8. Acceptance criteria

명령은 모두 저장소 루트에서 Python 3.12로 실행한다.

- A-1 루트 `pyproject.toml`의 `[project].dependencies`에 이름이 `nolemy-`로 시작하는 요구가 없고, `rustworkx>=0.17,<0.18`, `fastembed>=0.8,<1`, `chromadb>=1.5.9,<2`가 있다. `[dependency-groups].dev`에 `nolemy-*` 5개가 있다. `[tool.uv.workspace]`와 `[tool.uv.sources]`는 `2bc19ca`와 같다.
- A-2 `uv lock --check`가 성공한다. 새로 만든 환경에서 `uv sync` 후 `ci.yml` `verify` 작업의 Lint, Type check, Test 명령(`ci.yml:66-71@2bc19ca`)이 모두 성공한다.
- A-3 빈 `dist/`에서 `uv build`를 실행하면 `vault_graph-<version>-py3-none-any.whl`과 `vault_graph-<version>.tar.gz` 2개만 생긴다. `python tests/verify_release_dist.py dist`가 성공한다. wheel 파일 목록에 `vault_graph/`와 모듈 5개의 `<import 이름>/__init__.py`가 있다.
- A-4 A-3의 sdist에서 다시 빌드한 wheel(`uv build --wheel <sdist 경로>`)의 파일 목록이 A-3 wheel의 파일 목록과 같다.
- A-5 `verify_release_dist.py`는 다음 세 경우에 각각 0이 아닌 종료 코드로 끝난다. (a) `dist/`에 `nolemy_*` wheel을 하나 추가했을 때, (b) wheel에서 모듈 하나를 뺐을 때, (c) `Requires-Dist`에 `nolemy-*`가 있을 때. 이 확인은 PR 설명에 실행 결과로 남긴다.
- A-6 `uv run --python 3.12 python tests/verify_graph_module_wheels.py`가 성공한다. vault venv에는 루트 wheel만 설치되고, 이름이 `nolemy-`로 시작하는 배포가 없으며, 모듈 5개의 `__init__.py`가 `importlib.metadata.files("vault-graph")`에 들어 있다. `install_from_local_simple_index`는 파일에 남아 있지 않다.
- A-7 `tests/test_root_dependency_alignment.py`가 일반 `pytest` 실행에 포함되어 성공한다. 이 파일에는 모듈 쪽에만 있는 외부 의존성을 주었을 때 실패를 보고하는 경우를 검사하는 테스트가 하나 이상 있다.
- A-8 `publish-pypi.yml`, `publish-testpypi.yml`, `prepare-release.yml`에 `--all-packages`가 들어간 빌드 명령과 `dist/nolemy_*`가 없다. 세 파일과 `ci.yml` `verify` 작업 모두 `Check distributions` 다음, 업로드 또는 Release 생성 전에 `verify_release_dist.py dist` 단계가 있다.
- A-9 `ci.yml`의 `graph-search-runtime-compatibility`와 `independent-modules` 작업(`ci.yml:13-60@2bc19ca`)은 바뀌지 않고, PR CI에서 모두 성공한다.
- A-10 범위 제한: `packages/**`와 `src/**` 아래 파일은 바뀌지 않는다(`git diff --stat main -- packages src`가 비어 있다). `publish.sh`도 바뀌지 않는다.
- A-11 `docs/PUBLISHING.md`가 PyPI에는 `vault-graph`만 올리고 모듈은 그 wheel에 포함된다고 적는다. `docs/ARCHITECTURE.md`에 "독립 배포 패키지"라는 표현이 남아 있지 않다. spec 승인 후 `docs/DECISIONS.md`에 새 항목이 Question/Decision/Reason/Implications 형식으로 추가된다.
- A-12 병합 후 배포 확인(수동): 9절 질문1에서 고른 버전의 `publish-pypi` 실행이 성공하고, PyPI에는 `vault-graph`만 새로 올라간다. `uv tool install vault-graph==<version>` 후 `vg --help`, `vg setup --help`, `vg ask --help`가 성공하고, 그 도구 환경에 `nolemy-*` 배포가 없다.

## 9. Open decisions

### 결정 기록 (spec gate, 2026-10-28)

- 설계 결정1~10: 사용자가 승인했다.
- 질문1: 옵션2 0.2.1로 올림 [사용자].
- 질문2: 옵션1 Release `v0.2.0`과 태그를 남기고 설명을 추가하며 `nolemy_*` 첨부 파일을 지운다 [사용자]. 이 작업은 병합 후 사람이 GitHub에서 직접 한다.
- 질문3: 옵션1 TestPyPI에서 먼저 확인한다 [사용자]. TestPyPI에 `vault-graph 0.2.1`이 없는 것을 2026-10-28에 확인했다.
- 질문4: 옵션1 `docs/DECISIONS.md`에만 기록한다 [가정, 사용자에게 알리고 진행].

아래는 gate 전에 제시한 선택지 원문이다.

### 질문1 이번 변경을 어떤 버전으로 배포할 것인가 (위험3)

- 옵션1 0.2.0 재사용
  - 절차: GitHub Release `v0.2.0`과 태그 `v0.2.0`을 삭제한다. 이 PR을 병합한 뒤 `prepare-release`를 `version: 0.2.0`으로 다시 실행한다.
  - 장점: 버전 파일이 이미 0.2.0이므로 버전 올림 PR이 필요 없다. PyPI 버전 번호에 빈칸이 생기지 않는다.
  - 단점: 이미 공개된 태그를 다른 커밋으로 옮긴다. 태그를 받아 간 사람의 로컬에는 옛 태그가 경고 없이 남는다. Release·태그 삭제를 사람이 직접 해야 하고, 빠뜨리면 `prepare-release.yml:63-71@2bc19ca`에서 멈춘다. PyPI에 0.2.0 파일이 하나도 없다는 전제(7절 6번)가 맞아야 한다.
- 옵션2 0.2.1로 올림
  - 절차: 이 PR을 병합한 뒤 `./publish.sh -v 0.2.1`로 버전 올림 PR을 만들고, 병합 후 `prepare-release`를 `version: 0.2.1`로 실행한다.
  - 장점: 태그를 옮기지 않는다. 기존 workflow 검사가 그대로 통과한다. "0.2.0은 배포 실패"라는 기록이 남는다.
  - 단점: PyPI 버전이 0.1.4 다음 0.2.1이 된다. 버전 올림 PR이 하나 더 필요하다.
- 추천: 옵션2. brief의 가정은 옵션1을 추천했지만, 옵션1은 공개된 태그를 옮기고 수동 삭제 단계를 더한다. 옵션2는 버전 번호 하나를 건너뛰는 비용만 있다.

### 질문2 옵션2를 고를 경우, 기존 GitHub Release `v0.2.0`을 어떻게 둘 것인가

- 옵션1 Release와 태그를 남기고, Release 설명에 "PyPI 배포 실패, 0.2.1로 대체"를 적고 첨부된 `nolemy_*` 파일을 지운다.
- 옵션2 Release만 지우고 태그는 남긴다.
- 추천: 옵션1. 실패 기록과 실행 40661532945로 가는 경로가 남고, 받을 수 없는 `nolemy_*` 파일을 사용자가 내려받지 않는다.

### 질문3 PyPI 배포 전에 TestPyPI로 먼저 확인할 것인가

- 옵션1 이 PR 병합 후 `publish-testpypi`를 실행하고, TestPyPI에서 설치해 `vg --help`를 확인한 뒤 PyPI 배포를 진행한다.
- 옵션2 TestPyPI를 건너뛰고 바로 PyPI 배포를 진행한다.
- 추천: 옵션1. `docs/PUBLISHING.md:96-108@2bc19ca`가 위험한 패키징 변경 전에 TestPyPI를 쓰라고 안내하고, 이번 변경이 그 경우다. 단, TestPyPI에 같은 버전이 이미 올라가 있으면 실패하므로 질문1에서 고른 버전이 TestPyPI에 없는지 먼저 확인해야 한다.

### 질문4 이번 변경을 `docs/PATCH_LOG.md`에도 기록할 것인가

- 옵션1 `docs/DECISIONS.md`에만 새 항목을 추가한다.
- 옵션2 `docs/DECISIONS.md` 항목과 함께, 배포 실패를 계기로 한 수정으로 `docs/PATCH_LOG.md` 항목도 추가한다.
- 추천: 옵션1. 이번 변경은 기존 spec과의 불일치를 고치는 것이 아니라 배포 방식을 바꾸는 정책 결정이다. AGENTS.md 기준으로 PATCH_LOG는 검증 중 발견한 불일치 수정에 쓴다.
