# Spec: install-onboarding (vault-builder + vault-graph 첫 설치 개선)

## 1. Problem

기준 사용자는 개인 Vault 1개와 앱 저장소용 project Vault 1개를 쓰는 Claude Code 사용자다. 이 사용자가 지금 처음 설치하려면 저장소 2개를 clone하고, 명령 6개 이상을 순서대로 실행하고, Claude Code를 종료했다가 다시 시작해야 한다(brief "Current first-install flow" 1~7단계). 아래 문제는 모두 코드와 문서에서 직접 확인했다.

| 코드 | 문제 | 근거 (확인 방법) |
|---|---|---|
| 발견1 | 시작 명령이 하나가 아니다. 첫 문서가 두 저장소에 흩어져 있다. vault-builder README "Simple Setup"의 `bootstrap.sh`는 Vault 폴더만 만들고 vg, hook, 저장소 연결은 하지 않는다. | `$HOME/workspace/vault-builder/scripts/bootstrap.sh` 전체를 읽음. 마지막 안내가 `health`와 `mcp_server.py`뿐이다. |
| 발견2 | vg를 vault-builder install 뒤에 설치하면 hook이 vg를 못 찾을 수 있다. 팀 요약의 "install 순서 때문에 hook이 빠진다"는 일부만 맞다. 실행 중 launcher는 `VAULT_GRAPH_BIN`, `vault-hooks.json`의 `vg`, `PATH` 순서로 찾으므로 Claude Code hook 프로세스의 `PATH`에 uv tool 폴더가 있으면 동작한다. GUI나 IDE에서 Claude Code를 시작해 그 폴더가 `PATH`에 없으면 recall.sh로 대체되고, 사용자는 원인을 알 수 없다. install 시점에 vg가 없으면 한 줄 note만 나온다. | `assets/vault-hooks/vault_hooks.py:17`, `:66-79`, `hooks.py:158-166`, `installing.py:494-500`. |
| 발견3 | 저장소 연결을 Vault마다 한 번씩 해야 한다. `link`는 Vault 이름 하나만 받는다. | `cli.py:585-589`, `linking.py:96-155`. |
| 발견4 | Vault마다 install을 따로 실행하고, install은 `$HOME/.claude.json`을 쓰므로 실행 전마다 Claude Code를 종료해야 한다. | `installing.py:17`, `:203-206`, usage.md §17.6. |
| 발견5 | [정정 2026-11-04] vault-graph는 PyPI에 있다(0.1.0~0.2.1, 최신 0.2.1은 2026-10-29 업로드, `https://pypi.org/pypi/vault-graph/json`로 확인). 다만 0.2.1에는 이 작업이 더하는 `vg mcp unregister`와 hook 상태 알림이 없어(`git grep unregister v0.2.1`), 설치 명령은 PyPI 버전을 쓸 수 없다. README의 clone 주소 `git@me.github.com:cutehackers/vault-graph.git`는 작성자 개인 SSH host 별칭이라 다른 사람의 컴퓨터에서는 그대로 동작하지 않는다. | vault-graph `README.md:35`, `:48-53`. |
| 발견6 | hook은 `install --with-hooks`를 줄 때만 설치된다. 팀 요약 순서에는 이 옵션이 없으므로 그대로 따라 한 사용자는 hook이 하나도 없고, 경고도 받지 않는다. 발견2보다 큰 공백이다. | vault-builder `tools/vault_migration/cli.py:565-566`, `installing.py:21-23`("Without --with-hooks install does not open that file"). |
| 발견7 | `vg setup`의 `--agent` 기본값이 `codex`이고 README Quick Start 첫 예시도 `--agent codex`다. Claude Code 사용자가 첫 예시를 따라 하면 MCP 서버가 Codex 설정에 등록된다. | vault-graph `src/vault_graph/interface/cli/main.py:419`, `README.md:60`. |
| 발견8 | hook 상태를 한 번에 검사하는 명령이 없다. vault-builder `doctor`는 Vault 하나를 받고 MCP, skill, recall을 보지만 hook 항목과 `vault-hooks.json`의 vg 경로는 보지 않는다. vg는 `vault-hooks.json`을 전혀 읽지 않는다. | usage.md §17.6 doctor 항목 목록, `cli.py:580-581`. vault-graph `src/`에서 `vault-hooks`를 검색해 결과 0건. |
| 발견9 | 나중 명령이 builder checkout 안에서만 실행된다. `link`, `doctor`, `set-default-write`는 `python3 tools/vault_migration/cli.py`로 실행하고, vg의 오류 메시지도 그 상대 경로를 안내한다. checkout 위치를 기억하지 못하면 다음 저장소 연결이 막힌다. | usage.md §17.3, vault-graph `src/vault_graph/operation/memory/memory_target.py:61-67`. |
| 발견10 | vault-graph에는 MCP 등록을 지우는 명령이 없다. 제거 절차가 문서에 없다. | vault-graph `src/vault_graph/operation/integration/mcp/`에서 `unregister` 검색 결과 0건. |

역할 처리는 이미 열려 있다. `install --role`과 `set-role`은 비어 있지 않은 문자열을 모두 받는다(`installing.py:329-332`, `map_settings.py:59-65`). 코드에서 동작이 달라지는 역할은 `project` 하나다. 세션 원문 저장과 기본 쓰기 Vault 자동 지정이 이 역할만 본다(`linking.py:24`, `:76-93`). vault-graph는 역할 문자열로 분기하지 않는다(`src/`에서 역할 값 비교 검색 결과 0건, `memory_target.py:6`). 반면 usage.md §17.1은 역할을 "3가지 가운데 하나"로 적어 문서와 코드가 다르다.

## 2. Intent

- 새 사용자는 두 저장소의 내부 구조를 몰라도 설치를 끝낸다. 처음 여는 문서(두 저장소의 README)가 같은 명령 하나를 안내한다.
- 첫 설치는 명령 1개와 Claude Code 재시작 1번으로 끝난다. 끝나면 MCP 서버, hook, 저장소 연결, 색인이 모두 동작한다.
- 저장소 하나를 연결할 때 명령 하나로 그 저장소가 쓸 Vault 전부를 연결한다.
- team Vault처럼 personal, project 말고 다른 역할의 Vault도 첫 설치와 Vault 추가 단계에서 함께 넣을 수 있다. 기준 사용자(personal + project)에게는 이 단계가 추가 명령을 요구하지 않는다(brief 답변 5, 6).
- 나중에 새 역할이 생겨도 설치·연결 명령의 사용법은 바뀌지 않는다(brief 답변 5).
- vg는 git 주소로 설치한다. PyPI 최신 버전(0.2.1)에는 설치 명령이 쓰는 명령이 없다(발견5). 저장소 권한이 있는 사람만 설치할 수 있어도 된다(brief 답변 2).
- 설계 결과는 두 저장소에 구현하고 PR까지 간다(brief 답변 1).
- [가정] 이미 설치한 사용자의 환경은 그대로 동작하고, 새 설치 명령을 다시 실행하면 빠진 부분(hook, vg 경로)만 채워진다.

## 3. Non-goals

- vault-graph의 새 PyPI 배포. PyPI에는 0.2.1까지 있다(발견5, brief 답변 2).
- Windows 지원 [가정].
- Codex 사용자의 원클릭 설치. 설치 명령은 Claude Code를 기준으로 한다. Codex 사용자는 지금처럼 `vg setup --agent codex`를 쓴다 [가정].
- `vg setup`의 `--agent` 기본값 변경. 기존 Codex 사용자의 동작이 바뀌기 때문이다. 설치 명령이 `--agent claude`를 명시하고, README가 Claude 예시를 먼저 보여 주는 것으로 대신한다.
- Vault 내용 구조, catalog, manifest 형식, `vault-map.json` 형식(version 2) 변경.
- vault-graph가 Vault 파일이나 `vault-map.json`을 쓰는 일. vault-graph는 계속 읽기만 한다(README Guarantees, AGENTS.md "Project Boundary").
- 역할별 새 동작(예: team Vault 전용 쓰기 규칙) 추가. 역할 문자열을 받아 저장하고 연결하는 것까지만 다룬다.
- Claude Code plugin으로의 전환. §4.1에서 비교하고 이번에는 채택하지 않는다.

## 4. Design

### 4.1 두 방식 비교

| 기준 | 옵션1: Claude Code plugin으로 묶기 | 옵션2: 지금 CLI를 유지하고 한 명령으로 묶기 |
|---|---|---|
| 첫 설치 명령 수 | plugin 추가는 셸에서도 marketplace 등록과 plugin 설치 두 명령이다(출처 3). 설치 때 실행되는 plugin hook이 없으므로 uv와 vg 설치가 따로 필요하다(출처 3). Vault 폴더 생성과 `vault-map.json` 작성도 plugin 설치만으로는 일어나지 않고 명령을 따로 실행해야 한다. 그래서 "명령 1개"를 맞추지 못한다. | 셸 명령 1개(`curl ... install.sh \| bash`)가 uv 확인, vg 설치, Vault 생성, hook, 연결, MCP 등록, 색인, 검사까지 한다. |
| 재시작 | `/reload-plugins`로 재시작 없이 적용할 수 있다(출처 3). | 끝난 뒤 1번. 실행 전에 Claude Code를 종료해 두는 것이 재시작 1번에 포함된다. |
| hook, MCP, skill 제공 | plugin 안의 `hooks/hooks.json`, `.mcp.json`, `skills/`로 제공할 수 있다(출처 1). | 지금처럼 install이 `$HOME/.claude/settings.json`, `$HOME/.claude.json`, `$HOME/.claude/skills/`에 쓴다. |
| 경로 | plugin 경로는 `${CLAUDE_PLUGIN_ROOT}`로 얻는다(출처 1). 설치된 plugin 폴더는 version마다 다르다(`$HOME/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, 이 컴퓨터의 bake 0.6.1과 0.6.2 폴더로 확인). vg 위치는 plugin이 알 수 없으므로 MCP 항목은 `PATH`의 `vg`에 기대야 하고, 이것이 발견2의 GUI `PATH` 문제를 그대로 남긴다 [가정]. | vg 절대 경로를 설치 때 구해 `vault-hooks.json`과 `mcpServers.vault-graph`에 적는다. 지금 코드가 이미 그렇게 한다(`hooks.py:158-170`, vault-graph README "Quick Start"). |
| 기존 사용자 | install이 이미 쓴 hook 항목, `llm-wiki` 서버, skill과 plugin이 주는 것이 겹친다. install, uninstall, doctor, manifest 기록을 다시 설계하고 이전 절차가 필요하다. | 같은 명령을 다시 실행하면 빠진 것만 채운다. 형식 변경이 없다. |
| 구현 범위 | 두 저장소의 설치 경로를 새로 만든다. | 새 코드는 설치 스크립트, 여러 단계를 차례로 실행하는 `setup` 명령, `link` 여러 Vault 지원, doctor 확장, vg의 hook 상태 보고와 MCP 등록 해제다. |
| Codex | plugin은 Claude Code 전용이다. | vg CLI는 그대로 Codex도 지원한다. |

추천: 옵션2. 옵션1은 Python 도구 설치와 Vault 생성을 plugin 밖에서 해야 하므로 성공 기준인 "명령 1개"를 구조상 맞추지 못한다. 그리고 vg 절대 경로를 기록하는 지금의 해법을 잃는다. 옵션2는 지금 형식을 바꾸지 않고 성공 기준을 맞춘다.

plugin 기능 출처:

1. Anthropic 공식 marketplace의 `plugin-dev` plugin 문서 로컬 사본: `$HOME/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/plugin-structure/SKILL.md` 20-37행(폴더 구조), 258-300행(`${CLAUDE_PLUGIN_ROOT}`), 341-353행(구성 요소 자동 발견, "다음 세션부터 적용").
2. 같은 plugin의 `skills/hook-development/SKILL.md` 576-582행: hook은 세션 시작 때 읽으므로 바꾸면 Claude Code를 재시작해야 한다.
3. 공식 문서(2026-11-03 확인):
   - 설치 때 실행되는 plugin hook은 없다. `Setup` hook은 `--init-only`, `--init`, `--maintenance` 실행 때만 동작한다(https://code.claude.com/docs/en/hooks.md). marketplace의 `command` source는 사용자가 수락하면 명령을 실행한다(https://code.claude.com/docs/en/plugins/install.md).
   - 셸에서 설치할 수 있다: `claude plugin marketplace add <owner>/<repo> --scope user`, `claude plugin install <plugin>@<marketplace>`. 비공개 저장소는 이 컴퓨터의 git 인증을 쓴다(같은 문서, https://code.claude.com/docs/en/plugins/cli-reference.md).
   - `/reload-plugins`가 있다. 재시작 없이 plugin의 hook, skill, MCP 서버를 적용한다(cli-reference.md).
   - `.mcp.json`의 `command`, `args`, `env`에 `${CLAUDE_PLUGIN_ROOT}`를 쓸 수 있다(https://code.claude.com/docs/en/mcp.md). plugin 밖 실행 파일(PATH의 `vg`, 절대 경로)을 가리킬 수 있는지는 문서에 없다.

옵션3(혼합): 셸 명령 하나가 uv, vg, Vault, 연결을 처리하고, hook, MCP, skill은 `claude plugin install`로 등록한다. 장점은 `$HOME/.claude.json`과 `settings.json`을 직접 고치지 않아 Claude Code를 종료하지 않아도 되고, 재시작 대신 `/reload-plugins`를 쓸 수 있다는 점이다. 단점은 세 가지다. 첫째, plugin MCP 서버가 plugin 밖 vg 절대 경로를 쓸 수 있는지 확인되지 않았다. 둘째, 기존 install이 쓴 hook, `llm-wiki` 서버, skill과 겹치므로 이전 절차가 필요하다. 셋째, install, uninstall, doctor, manifest 기록을 다시 설계해야 한다. 성공 기준(명령 1개 + 재시작 1번)은 옵션2로도 맞으므로 이번에는 옵션2를 추천하고, 옵션3은 "Claude Code 종료 없이 설치"가 필요해질 때 다음 작업으로 둔다.

### 4.2 전체 구성 (옵션2)

```
README(두 저장소) ─▶ 설치 명령: curl -fsSL .../vault-builder/main/scripts/install.sh | bash
                     │  (bash: 필수 도구 확인, builder checkout 준비, vault-builder 명령 설치)
                     ▼
                   vault-builder setup  (Python, tools/vault_migration/onboarding.py)
                     1 사전 검사(읽기만) ─ 2 vg 설치 ─ 3 Vault마다 install --with-hooks
                     ─ 4 저장소 연결(link 한 번) ─ 5 vg setup --agent claude --mcp ─ 6 doctor
                     ▼
                   "Claude Code를 다시 시작하세요" + 확인 방법
```

용어:

- 설치 명령: README에 적는 셸 명령 하나. 내용은 `scripts/install.sh`다.
- `vault-builder` 명령: 설치 명령이 `$HOME/.local/bin/vault-builder`에 두는 짧은 실행 파일. builder checkout의 `tools/vault_migration/cli.py`를 실행한다. 다음 Vault 추가, 다음 저장소 연결, 검사, 제거를 이 명령으로 한다(발견9).
- builder checkout: 설치 명령이 만드는 vault-builder git checkout. 기본 위치는 `$HOME/.local/share/vault-builder`다 [가정].
- 역할 목록: vault-builder `tools/vault_migration/roles.py` 한 파일에 둔 알려진 역할 표(§4.6).

### 4.3 설치 명령 `scripts/install.sh` (vault-builder, 새 파일)

- 하는 일: `git`, `curl`, Python 3.10 이상을 확인한다. Python 고르는 규칙은 `bootstrap.sh`의 `choose_python`과 같다. uv가 없으면 §5 결정4에 따라 처리한다. builder checkout을 만들거나 `git pull --ff-only`로 갱신하고, `vault-builder` 명령을 만든 뒤 `vault-builder setup "$@"`을 실행한다.
- 저장소와 ref는 `VAULT_BUILDER_REPO`, `VAULT_BUILDER_REF` 환경 변수로 바꿀 수 있다. `bootstrap.sh:4-5`와 같은 이름이다.
- `curl | bash`로 실행되면 stdin이 스크립트이므로, 질문은 `/dev/tty`에서 읽는다. `/dev/tty`가 없으면 비대화 모드로 실행한다.
- `bootstrap.sh`와 `init-vault.sh`는 그대로 둔다. README에서는 "Vault 폴더만 만들기"로 소개한다.

- 설치는 두 종류다. 둘 다 같은 설치 명령으로 시작한다.
  1. 전체 설치(기본): vault-builder와 vault-graph를 함께 설치한다. vault-graph는 따로 설치하지 않고 이 명령 안에서 vault-builder가 설치한다(사람 답변 2026-11-04).
  2. vault-builder만 설치: `--without-vault-graph`. vg, `mcpServers.vault-graph`, vg 색인 없이 Vault, hook, 저장소 연결, `llm-wiki` MCP 서버만 설치한다. vault-builder는 vault-graph 없이도 완전히 동작해야 한다(사람 답변 2026-11-04). 대화 모드는 "vault-graph(여러 Vault 검색과 세션 시작 회상)도 설치할까요 [예]"로 묻는다.
  3. vault-builder만 설치한 뒤 vault-graph를 더하려면 같은 설치 명령(또는 `vault-builder setup`)을 `--without-vault-graph` 없이 다시 실행한다. vg가 설치되고 hook의 vg 경로가 기록된다.
- `vault-builder` 명령의 생애는 설치 명령이 관리한다(사람 답변 2026-11-04).
  1. 설치: 설치 명령이 `$HOME/.local/bin/vault-builder`를 만든다. 파일 안에 builder가 만들었다는 표시 줄과 builder checkout 경로를 적는다. 다시 실행하면 같은 내용이면 그대로 두고, 표시 줄이 있는 이전 내용이면 교체한다.
  2. 같은 경로에 표시 줄이 없는 파일이 있으면 건드리지 않고 멈춘다.
  3. 제거: `install.sh --uninstall`과 `vault-builder uninstall --all`의 마지막 단계가 표시 줄이 있는 `vault-builder` 파일만 지운다. builder checkout도 함께 지운다. `VAULT_BUILDER_HOME`으로 사용자가 고른 checkout은 지우지 않는다.
  4. `vault-builder doctor`는 이 파일이 있고 기록된 checkout을 가리키는지 검사한다.

### 4.4 `vault-builder setup` (vault-builder, 새 하위 명령)

서명: `setup [--vault NAME=PATH]... [--role NAME=ROLE]... [--repo PATH]... [--project-vault NAME=PATH] [--default-write NAME] [--yes] [--dry-run] [--without-vault-graph]`

- `--vault`를 여러 번 줄 수 있다. 개수와 역할 제한이 없다. 첫 설치에서 team Vault나 다른 역할의 Vault를 같은 실행에 더한다.
- `--role NAME=ROLE`은 Vault마다 역할을 정한다. 비어 있지 않은 문자열이면 무엇이든 받는다(지금 install 규칙과 같다). 없으면 새 Vault는 `personal`, 이미 등록된 Vault는 지금 역할을 유지한다(`installing.py:326`, usage.md §17.2).
- `--project-vault NAME=PATH`는 `--repo`가 하나일 때 그 저장소의 project Vault를 만든다. 역할은 `project`다. 기준 사용자를 위한 줄임 옵션이다.
- `--repo`를 주면 4단계에서 그 저장소를 연결한다.
- 대화 모드(옵션 없이 실행, tty 있음)는 아래 순서로 묻는다. 대괄호 안이 Enter를 누를 때 쓰는 값이다.
  1. 개인 Vault 경로 [`$HOME/vault`]. 이미 `vault-map.json`에 Vault가 있으면 이 질문을 건너뛰고 등록된 Vault 목록을 보여 준다.
  2. 연결할 저장소 경로 [현재 폴더가 git 저장소이면 그 폴더, 아니면 건너뜀].
  3. 그 저장소의 project Vault를 만들지 [예, 경로 `$HOME/vaults/<저장소 폴더 이름>`, 이름 `<저장소 폴더 이름>`] [가정].
  4. 다른 Vault를 더 추가할지 [아니오]. 예를 고르면 경로, 이름, 역할을 묻는다. 역할 질문은 역할 목록의 이름과 설명을 보여 주고, 목록에 없는 문자열도 받는다. 이 질문을 반복한다.
  5. 실행할 계획을 보여 주고 진행할지 [예].
- 기준 사용자는 질문 1~5에 모두 Enter를 누르면 된다. 비대화 모드에서 같은 결과를 내는 명령은 `curl ... | bash -s -- --repo /path/app --yes`다.

단계:

1. 사전 검사. 파일을 쓰지 않는다. 옵션을 해석하고, `vault-map.json`을 읽고, Vault마다 `install --dry-run`과 같은 precheck를 실행하고, vault-graph 저장소 접근(`git ls-remote`)을 확인하고, Claude Code 실행 여부를 확인한다(§5 결정5). 하나라도 실패하면 아무것도 쓰지 않고 멈춘다.
2. vg 설치. `uv tool install --force git+<vault-graph 주소>`를 실행한다. 주소 기본값은 `https://github.com/cutehackers/vault-graph.git`이고(결정3) `VAULT_GRAPH_REPO`로 바꾼다. 설치된 vg 절대 경로는 `uv tool dir --bin`으로 구한다. `--without-vault-graph`를 주면 이 단계와 5단계를 건너뛴다.
3. Vault마다 `install <PATH> --name <NAME> [--role <ROLE>] --with-hooks`를 실행한다. 이때 `VAULT_GRAPH_BIN=<2단계 vg 절대 경로>`를 넘겨 `vault-hooks.json`에 vg 절대 경로를 적는다. 그래서 vg를 먼저 설치하고 Vault를 나중에 설치하는 순서가 고정된다(발견2, 발견6). install 순서는 지정된 순서이고 Claude Code 종료는 한 번만 확인한다(발견4).
4. 저장소 연결. 저장소마다 `link --repo <PATH> <NAME>...`을 한 번 실행한다(§4.5).
5. `vg setup --agent claude --mcp`를 2단계의 vg 절대 경로로 실행한다. `--vault`를 주지 않으므로 `vault-map.json`의 모든 Vault를 색인한다(`main.py:432`, `:468-486`).
6. `doctor`(경로 없음, §4.7)를 실행하고 결과를 요약한다.
7. 마지막 줄들: "Claude Code를 다시 시작하세요", `/mcp`에서 `llm-wiki`와 `vault-graph`가 보이는지 확인하는 방법, 다음 저장소 연결 명령 `vault-builder link --repo <경로>`.

같은 `setup`을 다시 실행해도 결과가 같다. 이미 있는 Vault는 install이 vault 밖 단계만 실행하고(`installing.py:8-9`), 이미 연결된 Vault는 `link`가 다시 더하지 않는다(`linking.py:140-141`). 그래서 중간에 실패하면 원인을 고치고 같은 명령을 다시 실행하면 된다. 다음 Vault 추가는 `vault-builder setup --vault team=$HOME/team-vault --role team=team --repo /path/app`처럼 같은 명령에 새 Vault만 넘긴다.

### 4.5 `link` 여러 Vault 지원 (vault-builder `cli.py`, `linking.py`)

서명: `link [VAULT ...] [--repo PATH] [--project ID] [--dry-run]`

- Vault 이름을 여러 개 받는다. 한 번의 읽기와 한 번의 쓰기로 모두 더한다. 기본 쓰기 Vault 규칙은 모두 더한 뒤 한 번 적용한다.
- 이름을 주지 않으면 공유 Vault 전부를 연결한다. 공유 Vault는 역할 목록에서 `per_repo`가 아닌 역할의 Vault, 그리고 역할 목록에 없는 역할의 Vault다(§5 결정7). 지금 `per_repo` 역할은 `project` 하나다. 그 저장소에 project Vault가 없으면 등록된 project Vault 이름과 `vault-builder link <이름> --repo <경로>` 명령을 한 줄로 안내한다.
- 이름 하나를 주는 지금 사용법은 그대로 동작한다.
- `setup`은 항상 이름을 명시해 호출한다. 공유 Vault 전부와 그 저장소용 project Vault다.

### 4.6 역할 목록과 기본 쓰기 Vault 규칙

- 새 파일 vault-builder `tools/vault_migration/roles.py`에 알려진 역할 표를 둔다. 항목은 이름, 한 줄 설명, `per_repo` 여부다. 처음 내용은 `personal`(공유), `team`(공유), `project`(per_repo)다. 이 표는 대화 모드 질문, `--role` 도움말, 이름 없는 `link`의 공유 Vault 선택, `list`와 `doctor` 출력에만 쓴다.
- 역할 검사는 지금처럼 "비어 있지 않은 문자열"로 둔다. 표에 없는 역할도 install, set-role, setup, link가 받는다.
- `linking._PROJECT_ROLE`은 이 표의 `project` 항목을 가리키도록 바꾼다. Vault 쪽 코드 `tools/wiki/lib/session_capture.py`의 역할 값은 Vault 안에 복사되는 코드라서 이 파일을 import하지 않고 지금 값을 유지한다.
- 새 역할 추가 방법: `roles.py`에 한 줄을 더하고 usage.md §17.2 표에 한 줄을 더한다. note를 그 Vault로 보내려면 memory-cleanup skill 문서에 규칙을 더한다. setup, install, link 코드와 설치 명령의 사용법은 바뀌지 않는다.
- 기본 쓰기 Vault 규칙은 바꾸지 않는다(`linking.py:76-93`). 저장소가 Vault를 2개 이상 연결하고 그중 역할 `project`가 정확히 하나이면 그 Vault를 기본 쓰기 Vault로 정한다. 이미 정한 값은 바꾸지 않는다.
- 역할이 `project`가 아닌 Vault(personal, team, 새 역할)는 자동으로 기본 쓰기 Vault가 되지 않는다. 연결된 Vault 중 project Vault가 없거나 2개 이상이면 기본값이 정해지지 않는다. 이때 `setup`은 대화 모드에서 기본 쓰기 Vault를 고르라고 묻고, 비대화 모드에서는 `--default-write NAME`을 쓰거나 `vault-builder set-default-write --project <id> --vault <이름>` 명령을 안내한다. 기본값이 없어도 vg는 쓰기 때마다 Vault를 묻는 지금 동작을 유지한다(`memory_target.py:47-58`).

### 4.7 검사: `doctor`와 `vg setup`의 hook 보고

- vault-builder `doctor [PATH]`: 경로를 생략할 수 있게 한다. 생략하면 `vault-map.json`의 모든 Vault를 검사하고, 공유 항목은 한 번만 검사한다. 새 검사 항목(어떤 파일도 쓰지 않는다):
  1. `settings.json`에 SessionStart, PreCompact, SessionEnd launcher 항목이 하나씩 있는지(`hooks.py:30-34`).
  2. launcher 파일이 있고 builder 원본과 같은지.
  3. `vault-hooks.json`의 `vg`가 절대 경로이고 실행 파일인지.
  4. 그 vg가 `vg --help`로 10초 안에 exit 0으로 끝나는지. vg에는 `--version` 옵션이 없다(`main.py`에서 검색 결과 0건).
  5. `$HOME/.claude.json`에 `mcpServers.vault-graph`가 있고 그 `command`가 실행 파일인지. 없으면 문제가 아니라 안내로 출력한다(vault-graph 없이 쓰는 사용자도 있다).
  6. 각 문제 줄 끝에 고치는 명령 하나를 붙인다. 대부분 `vault-builder setup`이다.
- vault-graph `vg setup`(`main.py:412-465`): 마지막 Vault 처리 뒤 `<설정 폴더>/vault-builder/vault-hooks.json`을 읽기만 해서 hook 상태를 한 줄로 보고한다(brief의 사용자 힌트). 경우는 셋이다. 파일이 없으면 "hook이 설치되지 않았다", `vg` 값이 없거나 실행 파일이 아니면 "hook이 vg를 찾지 못한다", 지금 실행 중인 vg와 경로가 다르면 "hook이 다른 vg를 쓴다". 각 경고에 `vault-builder setup` 명령을 붙인다. 결과는 `warning:` 줄이고 exit 값은 바꾸지 않는다. `<설정 폴더>`는 `vault_map_path`와 같은 규칙(`CLAUDE_CONFIG_DIR`, 없으면 `$HOME/.claude`)으로 구한다(`vault_map.py:146-150`).
- vault-graph와 vault-builder 안내 문구 변경: `memory_target.py:67`의 `set-default-write` 안내와 recall 스크립트의 "연결되지 않은 저장소" 안내(usage.md §17.5 표)를 `vault-builder ...` 명령으로 바꾼다.

### 4.8 제거

- vault-builder `uninstall --all`: `vault-map.json`의 Vault마다 지금 `uninstall`을 실행한다. 마지막 Vault에서 공유 파일과 hook이 지워진다(`uninstalling.py:11-13`, `:403-404`). Vault 폴더의 `raw/`, `wiki/`는 지우지 않는다(usage.md §17.6).
- vault-graph에 `vg mcp unregister --agent claude [--config-path PATH] [--dry-run]`을 더한다. `mcpServers.vault-graph` 항목만 지우고 백업을 남긴다. `register`와 같은 파일 규칙을 쓴다(`mcp_config_registration.py:151-154`).
- 설치 명령 `install.sh --uninstall`: `vault-builder uninstall --all`, `vg mcp unregister --agent claude`, `uv tool uninstall vault-graph`를 차례로 실행하고, `vault-builder` 명령과 builder checkout을 지운다. Vault 폴더와 vg Data Home(`$HOME/.vault-graph`)은 지우지 않고 경로만 출력한다. 실행 전에 Claude Code 종료를 확인한다.

### 4.9 기존 사용자

- 아무것도 하지 않아도 지금 설치는 그대로 동작한다. 파일 형식을 바꾸지 않는다.
- 새 흐름으로 옮기려면 Claude Code를 종료하고 설치 명령을 한 번 실행한 뒤 재시작한다. `setup`은 `vault-map.json`의 기존 Vault를 그대로 쓰고, hook이 없으면 더하고, vg 경로를 기록하고, vg를 git 주소로 다시 설치한다. 기존 editable 설치(`uv tool install -e .`)는 `--force` 설치로 교체된다. 개발자는 `--without-vault-graph`로 이를 피한다.
- 기존 builder checkout이 다른 위치에 있어도 쓸 수 있다. `VAULT_BUILDER_HOME=<경로>`를 주면 설치 명령이 그 checkout을 쓰고 새로 clone하지 않는다.

### 4.10 첫 문서

- vault-builder `README.md`, `README-kr.md`: 첫 절을 "설치"로 바꾸고 설치 명령 한 줄, 끝난 뒤 할 일(Claude Code 재시작, `/mcp` 확인), 다음 저장소 연결 명령, vault-graph 저장소 권한이 없을 때(`--without-vault-graph`)를 적는다. `bootstrap.sh`는 "Vault 폴더만 만들기" 절로 옮긴다.
- vault-builder `docs/usage.md` §1: 같은 설치 명령으로 시작한다. §16, §17: `python3 tools/vault_migration/cli.py ...` 예시를 `vault-builder ...`로 바꾸고, 같은 동작을 builder checkout에서 직접 실행하는 방법은 한 줄로 남긴다. §17.1의 "역할 3가지 가운데 하나"를 "비어 있지 않은 문자열, 알려진 역할은 §17.2 표"로 고친다. §17.3에 여러 Vault `link`와 이름 없는 `link`를 적는다. §17.6에 `--all`, 새 doctor 항목, hook이 기본으로 설치된다는 점을 적는다.
- vault-graph `README.md` "Install": Claude Code 사용자는 vault-builder 설치 명령을 쓰라고 먼저 안내한다. vg만 설치하는 방법은 `uv tool install git+https://github.com/cutehackers/vault-graph.git`로 적는다(발견5, 결정3). "Quick Start"는 `--agent claude` 예시를 먼저 둔다(발견7). 개발용 editable 설치는 아래 절로 옮긴다.

## 5. Decisions

| 코드 | 결정 | 이유 | 누가 |
|---|---|---|---|
| 결정1 | 옵션2(지금 CLI 유지 + 한 명령)를 쓴다. | §4.1. plugin은 uv, vg 설치와 Vault 생성을 하지 못해 "명령 1개"를 맞추지 못하고, vg 절대 경로 기록을 잃는다. | 사람이 정했다(§9 질문1, 2026-11-03). |
| 결정2 | 설치 명령은 vault-builder 저장소(`scripts/install.sh`)에 둔다. | vault-builder는 인증 없는 `codeload.github.com`으로 내려받는다(`bootstrap.sh:133`). vault-graph도 공개 저장소라 HTTPS로 받는다(결정3). 입구는 누구나 받을 수 있는 쪽에 둔다. | [가정] |
| 결정3 | vg는 `uv tool install --force git+https://github.com/cutehackers/vault-graph.git`로 설치한다. | 사람이 git 주소 설치를 정했다(brief 답변 2). 저장소가 공개라서(`gh repo view --json visibility` 결과 PUBLIC, 2026-11-04) HTTPS 주소는 SSH 키 없이 동작한다(위험5). | 설치 방식은 사람, HTTPS 주소도 사람(2026-11-04 "Switch to HTTPS") |
| 결정4 | uv가 없으면 대화 모드에서 설치 여부를 묻고, 예이면 uv 공식 설치 스크립트를 실행한다. 비대화 모드에서는 설치 명령 한 줄을 출력하고 멈춘다. `--install-uv`를 주면 묻지 않고 설치한다. | 묻고 설치하면 기준 사용자의 명령 수가 1개로 유지된다. 사용자 모르게 도구를 설치하지 않는다. | 사람이 정했다(§9 질문3, 2026-11-03) |
| 결정5 | Claude Code가 실행 중이면 `$HOME/.claude.json`을 쓰는 단계 전에 멈춘다. 대화 모드는 "종료한 뒤 Enter"를 기다리고 다시 확인한다. 비대화 모드는 exit 3으로 끝낸다. 확인을 건너뛰는 옵션은 두지 않는다. | 실행 중인 Claude Code와 쓰기가 겹치면 한쪽 변경이 사라진다(usage.md §17.6). 종료를 한 번만 확인하므로 재시작은 1번이다. | 사람이 정했다(§9 질문4, 2026-11-03) |
| 결정6 | `setup`은 hook을 항상 설치한다(`install --with-hooks`). | 발견6. hook이 없으면 vg recall과 세션 원문 저장이 조용히 빠진다. 지금 `install` 명령의 기본값은 바꾸지 않아 기존 스크립트 사용자는 영향이 없다. | [가정] |
| 결정7 | 이름 없는 `link`는 `per_repo`가 아닌 역할과 역할 목록에 없는 역할의 Vault를 모두 연결한다. project Vault는 이름으로만 연결한다. | project Vault는 한 저장소의 이력이라 다른 저장소에 연결하면 안 된다. 다른 역할은 여러 저장소가 함께 쓴다(usage.md §17.2). 새 역할이 표에 없어도 연결 흐름이 막히지 않는다. | 사람이 정했다(§9 질문5, 2026-11-03) |
| 결정8 | 역할은 계속 자유 문자열이다. 알려진 역할 표는 안내와 공유 여부에만 쓴다. | 지금 코드가 이미 자유 문자열을 받는다(`map_settings.py:59-65`). 사람은 새 역할을 나중에 더할 수 있기를 원했다(brief 답변 5). | 방향은 사람, 위치는 [가정] |
| 결정9 | 기본 쓰기 Vault 자동 규칙은 바꾸지 않는다. project가 아닌 역할은 자동 기본값이 되지 않는다. 정해지지 않으면 대화 모드에서 묻는다. | 지금 규칙(`linking.py:76-93`)은 vault-graph 쓰기 대상 규칙(`memory_target.py:3-6`)과 맞물려 있다. 역할을 보고 쓰기 대상을 고르지 않는다는 vault-graph 결정(결정12, 결정15)을 지킨다. | [가정] |
| 결정10 | vault-builder 쪽 다음 작업은 `vault-builder` 명령 하나로 한다. 실행 파일은 `$HOME/.local/bin/vault-builder`이고 설치 명령이 만들고 제거 명령이 지운다(§4.3). | 사람이 정했다(2026-11-04). 발견9. uv도 같은 폴더에 실행 파일을 두므로 `PATH` 안내를 하나로 합칠 수 있다 [가정]. | 사람이 정했다(§9 질문2, 2026-11-03) |
| 결정11 | 비대화 모드의 project Vault 기본 경로는 `$HOME/vaults/<저장소 폴더 이름>`이다. 개인 Vault 기본 경로는 `$HOME/vault`다. | 개인 Vault 경로는 usage.md §17.6 예시와 같다. project Vault 경로는 정해진 관례가 없어 새로 정한다. | 사람이 정했다(§9 질문6, 2026-11-03) |
| 결정12 | vault-graph는 hook 상태를 읽기만 하고 고치지 않는다. 고치는 일은 vault-builder `setup`이 한다. | vault-graph는 Vault 쪽 설정을 쓰지 않는다(AGENTS.md "Project Boundary"). hook 파일은 vault-builder가 만들고 지운다(`hooks.py:8`). | [가정] |
| 결정13 | 설치는 전체 설치(기본)와 vault-builder만 설치 두 종류다. vault-graph는 vault-builder 설치 명령으로만 설치한다. | 사람이 정했다(2026-11-04). vault-builder는 vault-graph 없이도 쓸 수 있어야 한다. 기본값을 전체 설치로 둔 것은 [가정]이다. | 사람, 기본값은 [가정] |

## 6. Failure and boundary behavior

| 상황 | 동작 | 출력과 exit |
|---|---|---|
| `git`, `curl`, Python 3.10 이상 중 하나가 없음 | `install.sh`가 아무것도 쓰지 않고 멈춘다. | 없는 도구 이름과 OS별 설치 명령 한 줄(`bootstrap.sh:80-100`과 같은 형식). exit 1 |
| uv 없음, 대화 모드 | 설치 여부를 묻는다. 아니오이면 멈춘다. | uv 설치 명령 한 줄. 아니오이면 exit 1 |
| uv 없음, 비대화 모드, `--install-uv` 없음 | 멈춘다. | uv 설치 명령 한 줄과 "`--install-uv`를 주면 자동 설치"라는 줄. exit 1 |
| builder checkout 위치에 git checkout이 아닌 폴더가 있음 | 건드리지 않고 멈춘다. | 그 경로와 `VAULT_BUILDER_HOME`으로 다른 위치를 주는 방법. exit 1 |
| builder checkout에 사용자 변경이 있어 `git pull --ff-only` 실패 | 갱신하지 않고 지금 checkout으로 계속한다. | 경고 한 줄과 checkout 경로. 계속 진행 |
| `$HOME/.local/bin`이 `PATH`에 없음 | 계속 진행한다. 이번 실행은 절대 경로로 부른다. | 마지막에 shell 설정 파일에 더할 `export PATH=...` 한 줄 |
| vault-graph 저장소 접근 실패(네트워크, GitHub 접속 불가) | 1단계에서 멈추고 아무것도 쓰지 않는다. | "vault-graph 저장소에 접근할 수 없다", HTTPS로 GitHub에 접속되는지 확인하라는 안내, 접속할 수 없을 때 `--without-vault-graph`로 vault-builder만 설치하는 방법. exit 1 |
| `--without-vault-graph` | 2단계와 5단계를 건너뛴다. hook은 설치하고 vg 경로는 적지 않는다. | hook이 recall.sh와 직접 capture를 쓴다는 줄(`installing.py:497-499`과 같은 뜻). exit 0 |
| `uv tool install` 실패 | 3단계 전에 멈춘다. 이미 있던 vg는 uv가 유지한다 [가정]. | uv 오류 원문 마지막 20줄과 같은 명령을 직접 실행하는 방법. exit 1 |
| Claude Code 실행 중 | 결정5. | "Claude Code를 모두 종료하세요(터미널, IDE 포함)". 대화 모드는 대기, 비대화 모드는 exit 3 |
| Vault 경로가 이미 Vault가 아닌 다른 내용이 있는 폴더 | 1단계 precheck에서 멈춘다. | install precheck 오류 원문. exit 1 |
| 기존 Vault의 audit 결과에 변경이 필요함 | 1단계에서 멈춘다. | install 오류 원문과 usage.md §1.1 audit/apply 안내. exit 1 |
| Vault 이름 중복, 이름 형식 오류 | 1단계에서 멈춘다. | 충돌한 이름과 `--vault NAME=PATH`로 다른 이름을 주는 방법. exit 1 |
| `--role` 값이 빈 문자열 | 1단계에서 멈춘다. | 지금 install 메시지(`installing.py:332`). exit 1 |
| 역할이 역할 목록에 없음 | 그대로 받는다. 공유 Vault로 다룬다(결정7). | "알려진 역할이 아니다, 공유 Vault로 연결한다"는 줄. exit 0 |
| 3단계 중간 Vault install 실패 | 그 Vault의 vault 밖 변경은 install이 되돌린다(`installing.py:4-6`). 앞 Vault는 남기고 멈춘다. | 실패한 Vault, 오류 원문, "원인을 고친 뒤 같은 명령을 다시 실행하라". exit 1 |
| `settings.json`이 JSON이 아니거나 `hooks` 형식이 다름 | 1단계에서 멈춘다. | `hooks.py:71-79` 메시지. exit 1 |
| `--repo`가 git 저장소가 아님 | 1단계에서 멈춘다. | `linking.py:114` 메시지. exit 1 |
| 저장소가 이미 다른 project id로 연결됨 | 그 id를 그대로 쓴다. | `link` 출력의 "found by ..." 줄 |
| project id가 다른 저장소와 충돌 | 1단계에서 멈춘다. | `linking.py:123-126` 메시지와 `--project` 안내. exit 1 |
| 연결 뒤 기본 쓰기 Vault가 정해지지 않음 | 대화 모드는 묻는다. 비대화 모드는 계속한다. | `set-default-write` 명령 한 줄. exit 0 |
| `vg setup` 중 한 Vault 색인 실패 | 다른 Vault 색인은 계속한다(`main.py:450-465`). `setup`은 6단계까지 진행한 뒤 실패로 끝낸다. | `setup_failed:` 줄과 `vg setup --vault-id <id>`로 그 Vault만 다시 하는 방법. exit 1 |
| 첫 색인에서 임베딩 모델 내려받기 실패(네트워크) | 위와 같다. | 위와 같다 |
| 6단계 doctor가 문제를 찾음 | 문제 목록을 출력하고 실패로 끝낸다. 이미 쓴 것은 되돌리지 않는다. | 문제마다 고치는 명령 한 줄. exit 1 |
| 같은 명령을 두 번 실행 | 바뀌는 것이 없다. | 각 단계가 "unchanged" 또는 같은 뜻의 줄. exit 0 |
| `CLAUDE_CONFIG_DIR`가 `$HOME` 밖 | 1단계에서 멈춘다. | `installing.py:210-213` 메시지. exit 1 |
| `/dev/tty` 없음(CI 등) | 비대화 모드로 실행한다. 필요한 값이 없으면 멈춘다. | 빠진 옵션 이름. exit 2 |
| `vg setup`이 `vault-hooks.json`을 읽지 못함(없음, JSON 오류) | 색인과 MCP 등록은 계속한다. | §4.7의 `warning:` 줄. exit 값 변화 없음 |
| `install.sh --uninstall` 중 한 Vault uninstall 실패 | 그 단계에서 멈추고 MCP 등록 해제와 vg 제거는 하지 않는다. | 실패한 Vault와 오류 원문. exit 1 |
| `vg mcp unregister`에서 항목이 없음 | 아무것도 쓰지 않는다. | `changed: False`. exit 0 |

## 7. What could be wrong

| 코드 | 확인하지 못한 사실 | 틀리면 생기는 일 |
|---|---|---|
| 위험1 | plugin MCP 서버가 plugin 밖 vg 절대 경로를 쓸 수 있는지 공식 문서에 없다(§4.1 출처 3). 나머지 plugin 사실은 공식 문서로 확인했다. | 옵션3(혼합)을 나중에 고를 때 vg를 plugin 안에 넣어야 할 수 있다. 이번 추천(옵션2)에는 영향이 없다. |
| 위험2 | Claude Code 실행 여부를 확실히 알아내는 방법. 터미널 `claude`는 프로세스 이름으로 찾을 수 있지만 IDE 확장과 데스크톱 앱의 프로세스 이름은 확인하지 않았다. | 실행 중인 Claude Code를 놓치면 `$HOME/.claude.json` 변경이 사라질 수 있다. doctor가 MCP 항목 누락으로 잡지만 사용자는 같은 명령을 한 번 더 실행해야 한다. |
| 위험3 | `uv tool install --force`가 실패할 때 기존 vg 설치가 남는지. | vg가 사라지면 hook은 recall.sh로 대체되고 MCP 서버 `vault-graph`는 시작하지 못한다. |
| 위험4 | `uv tool dir --bin` 결과가 Claude Code hook 프로세스에서도 실행 가능한 경로인지(심볼릭 링크, 권한). | `vault-hooks.json`에 적힌 경로가 실행되지 않아 발견2가 남는다. doctor 항목 3과 4가 잡는다. |
| 위험5 | [해결 2026-11-04] 저장소는 공개다. 설치 주소를 HTTPS로 바꿨다(결정3). | SSH 키가 없는 사용자도 막히지 않는다. 다른 주소는 `VAULT_GRAPH_REPO`로 줄 수 있다. |
| 위험6 | 다른 위치의 오래된 builder checkout으로 설치한 사용자가 새 checkout으로 `setup`을 실행할 때, 라우터와 skill 파일 내용이 version 차이로 달라 install이 교체하거나 "알 수 없는 내용"으로 남길 수 있다(`installing.py:493`). | 공유 파일이 섞인 version으로 남는다. doctor가 내용 차이를 보고한다. |
| 위험7 | 이름 없는 `link`가 역할 목록에 없는 역할을 공유로 보는 규칙(결정7). 사용자가 저장소 하나에만 쓰려고 만든 새 역할의 Vault가 다른 저장소에도 연결될 수 있다. | 그 Vault 내용이 다른 저장소 세션의 검색과 recall에 보인다. |
| 위험8 | `$HOME/.local/bin`이 macOS 기본 shell의 `PATH`에 없을 수 있다. uv 설치 스크립트가 이 폴더를 `PATH`에 더하는지 확인하지 않았다. | 다음 작업에서 `vault-builder` 명령을 찾지 못한다. 설치 명령이 `export` 한 줄을 안내한다. |
| 위험9 | 첫 색인 시간. 임베딩 모델을 처음 내려받으므로 설치 명령 전체 시간이 길어질 수 있다(README "Quick Start" 끝 문단). 2026-11-04 측정(spec `2026-11-04-embedding-model-selection` §7 4번): 모델 `e5-small` 다운로드 약 135MB, Vault 6개 26,209조각의 전체 색인 약 14분, 메모리 최대 약 21GB. 기준 사용자(Vault 2개)의 첫 색인 시간은 재지 않았다. | 사용자가 멈춘 줄 알고 중단할 수 있다. 단계마다 진행 줄을 출력해야 한다. |

## 8. Acceptance criteria

성공 기준 "명령 1개 + 재시작 1번" (brief 답변 4):

- A-1. 빈 `HOME`(Vault, `vault-map.json`, `$HOME/.claude.json`, vg가 없음)에서 Claude Code를 종료한 상태로 README에 적힌 설치 명령 한 줄(`--repo <앱 저장소>` 포함)을 실행하고 질문마다 Enter만 누르면 exit 0으로 끝난다. 이 뒤에 사용자가 실행하는 명령 없이 Claude Code를 한 번 시작하면 A-2~A-5가 성립한다.
- A-2. A-1 뒤 `vault-map.json`에 역할 `personal` Vault 1개와 역할 `project` Vault 1개가 있다. 앱 저장소 project 항목의 `vaults`에 둘 다 있고, `default_write_vault`는 project Vault다.
- A-3. A-1 뒤 `$HOME/.claude.json`에 `mcpServers.llm-wiki`와 `mcpServers.vault-graph`가 있다. `vault-graph`의 `command`는 실행 가능한 vg 절대 경로다.
- A-4. A-1 뒤 `$HOME/.claude/settings.json`에 SessionStart, PreCompact, SessionEnd launcher 항목이 하나씩 있다. `$HOME/.claude/vault-builder/vault-hooks.json`의 `vg`가 A-3의 vg와 같은 절대 경로다.
- A-5. A-1 뒤 `PATH`에 uv tool 폴더가 없는 환경에서 launcher `session-start`를 앱 저장소 cwd로 실행하면 recall.sh가 아니라 `vg hook session-start`의 출력이 나온다(발견2).
- A-6. A-1 뒤 `vault-builder doctor`가 exit 0이다.
- A-7. 비대화 모드 `install.sh --repo <앱 저장소> --yes`가 `/dev/tty` 없이 A-2~A-6과 같은 결과를 낸다.

저장소 연결:

- A-8. Vault 3개(personal, team, project)가 등록된 상태에서 새 저장소에 `vault-builder link --repo <저장소> personal team <project>`를 한 번 실행하면 세 Vault가 모두 연결되고 `vault-map.json` 쓰기는 한 번이다.
- A-9. 이름 없는 `vault-builder link --repo <저장소>`는 역할이 `project`가 아닌 Vault를 모두 연결하고, `project` Vault는 연결하지 않으며, project Vault 연결 명령을 한 줄로 안내한다.
- A-10. 이름 하나를 주는 기존 `link <vault> --repo <저장소>` 사용의 출력과 결과가 지금과 같다(기존 테스트 통과).

역할 확장 (brief 답변 5, 6):

- A-11. 첫 설치 한 번의 실행(`--vault team=<경로> --role team=team` 추가)으로 personal, project, team Vault가 모두 설치되고 연결된다. 명령 수는 1개 그대로다.
- A-12. 역할 목록에 없는 역할(예: `client`)로 `setup`을 실행하면 exit 0이고 그 Vault가 공유 Vault로 연결된다. setup, install, link의 코드 변경 없이 동작한다.
- A-13. `roles.py`에 역할 한 줄을 더하는 것만으로 대화 모드 역할 질문과 `--role` 도움말에 그 역할이 보인다(테스트로 확인).
- A-14. personal과 team만 연결된 저장소는 `default_write_vault`가 자동으로 정해지지 않는다. 비대화 모드는 `set-default-write` 안내 한 줄을 출력한다. `--default-write team`을 주면 그 값이 기록된다.

검사와 실패:

- A-15. `settings.json`에서 launcher 항목 하나를 지우면 `vault-builder doctor`가 exit 1과 그 이벤트 이름, `vault-builder setup` 안내를 출력한다.
- A-16. `vault-hooks.json`의 `vg`를 없는 경로로 바꾸면 `vault-builder doctor`는 exit 1, `vg setup`은 exit 0과 `warning:` 줄 하나를 출력한다.
- A-17. `vault-hooks.json`이 없으면 `vg setup`이 "hook이 설치되지 않았다"는 `warning:` 줄을 출력한다. vg는 그 파일과 `settings.json`을 쓰지 않는다(파일 hash 비교 테스트).
- A-18. vault-graph 저장소 접근이 실패하는 환경에서 설치 명령은 exit 1로 끝나고, `vault-map.json`, `$HOME/.claude.json`, `settings.json`, Vault 폴더가 하나도 생기거나 바뀌지 않는다.
- A-19. Claude Code가 실행 중인 것으로 감지되면 비대화 모드는 exit 3으로 끝나고 `$HOME/.claude.json`은 바뀌지 않는다.
- A-20. 3단계에서 두 번째 Vault install이 실패한 뒤 원인을 없애고 같은 명령을 다시 실행하면 A-2~A-6이 성립한다.
- A-21. A-1을 마친 상태에서 같은 명령을 다시 실행하면 exit 0이고 `vault-map.json`, `$HOME/.claude.json`, `settings.json`의 bytes가 바뀌지 않는다.

다음 Vault, 제거, 기존 사용자:

- A-22. A-1 뒤 `vault-builder setup --vault team=<경로> --role team=team --repo <앱 저장소>` 한 명령으로 team Vault가 설치, 연결, 색인되고 hook과 MCP 항목은 바뀌지 않는다.
- A-23. `install.sh --uninstall` 뒤 `mcpServers.llm-wiki`, `mcpServers.vault-graph`, launcher hook 항목, `vault-map.json`, `vault-builder` 명령이 없고, Vault 폴더의 `raw/`, `wiki/`와 `$HOME/.vault-graph`는 남는다.
- A-24. `vg mcp unregister --agent claude`는 `mcpServers.vault-graph`만 지우고 다른 key는 그대로 두며 백업 파일을 남긴다. `--dry-run`은 파일을 쓰지 않는다.
- A-25. 지금 방식(hook 없이 install, editable vg)으로 설치한 환경에서 설치 명령을 한 번 실행하면 hook이 추가되고, 기존 Vault, 연결, `default_write_vault`는 그대로이며, A-6이 성립한다.

vault-builder만 설치와 명령 관리:

- A-31. `--without-vault-graph`로 빈 `HOME`에 설치하면 exit 0이다. vg와 `mcpServers.vault-graph`가 없고, `mcpServers.llm-wiki`, hook launcher 항목, `vault-map.json` 연결이 있으며, `vault-builder doctor`가 exit 0이다. launcher `session-start`는 recall.sh 출력을 낸다.
- A-32. A-31 뒤 `--without-vault-graph` 없이 같은 명령을 다시 실행하면 A-3, A-4가 성립한다.
- A-33. 설치 명령이 `$HOME/.local/bin/vault-builder`를 만들고, 제거 명령이 그 파일을 지운다. 표시 줄이 없는 같은 이름 파일이 있으면 설치는 그 파일을 바꾸지 않고 exit 1로 멈추고, 제거는 그 파일을 지우지 않는다.

범위와 호환:

- A-26. Vault 안 파일, `vault-map.json` version 2 형식, manifest 형식, `install`의 `--with-hooks` 기본값(꺼짐), `vg setup`의 `--agent` 기본값(`codex`)이 바뀌지 않는다.
- A-27. 실행 환경은 macOS와 Linux의 bash, zsh다. Windows는 검사 대상이 아니다.
- A-28. 설치 명령은 vault-graph를 PyPI가 아니라 git 주소로 설치한다.
- A-29. vault-builder README, README-kr, usage.md §1의 첫 설치 안내가 같은 설치 명령 한 줄이고, vault-graph README "Install"의 첫 안내가 그 명령을 가리킨다. vault-graph README "Quick Start"의 첫 예시는 `--agent claude`다.
- A-30. 두 저장소의 기존 테스트와 lint, 타입 검사가 통과한다.

## 9. Open decisions (모두 결정됨, 2026-11-03~04: 질문1~6 모두 추천안. 질문2는 "설치·삭제 기능으로 관리"를 더함, §4.3)

### 질문1. 설치 방식을 "지금 CLI 유지 + 한 명령"으로 정할까?

- 배경: 지금 설치는 두 저장소의 명령 6개 이상과 재시작이 필요하다. Claude Code plugin으로 묶는 방식과 지금 명령을 하나로 묶는 방식을 비교했다(spec §4.1). plugin 기능은 공식 문서로 확인했다(§4.1 출처 3).
- 바뀌는 것:
  1. 새 사용자는 셸 명령 한 줄을 실행하고 Claude Code를 한 번 다시 시작한다.
  2. 기존 사용자의 설치 파일 형식은 바뀌지 않는다.
- 틀리면: Claude Code를 끄지 않고 설치하는 경험(옵션3, §4.1)을 이번에는 놓친다.
- 추천: CLI 유지 + 한 명령. plugin은 uv와 vg 설치, Vault 생성을 하지 못해 "명령 1개"를 맞추지 못하고, vg 절대 경로 기록도 잃는다.
- 옵션1: CLI 유지 + 한 명령. 이 spec대로 진행한다. plugin 배포는 하지 않는다.
- 옵션2: plugin. spec §4를 다시 쓴다. 공식 문서 확인이 먼저 필요하고, 기존 사용자 이전 절차를 새로 만든다.

### 질문2. 나중 작업용 명령을 `$HOME/.local/bin/vault-builder`로 둘까?

- 배경: 지금 `link`, `doctor`는 builder checkout 폴더 안에서 `python3 tools/vault_migration/cli.py`로 실행한다. checkout 위치를 잊으면 다음 저장소를 연결하지 못한다.
- 바뀌는 것:
  1. 어느 폴더에서나 `vault-builder link --repo .`처럼 실행한다.
  2. vg 오류 메시지와 문서도 이 명령을 안내한다.
- 틀리면: 같은 이름의 다른 프로그램이 이미 있으면 덮어쓰거나 설치가 멈춘다.
- 추천: `vault-builder` 이름, `$HOME/.local/bin` 위치. uv가 vg를 두는 폴더와 같아 `PATH` 안내가 하나로 끝난다.
- 옵션1: 추천대로 한다. 같은 경로에 builder가 만들지 않은 파일이 있으면 멈춘다.
- 옵션2: 명령을 만들지 않는다. 문서에 checkout 경로를 적는다. 발견9가 남는다.

### 질문3. uv가 없을 때 설치 명령이 uv를 설치해도 될까?

- 배경: vg 설치에 uv가 필요하다. 새 사용자 중 uv가 없는 사람이 많다.
- 바뀌는 것:
  1. 대화 모드에서 "uv를 설치할까요"를 묻고, 예이면 uv 공식 설치 스크립트를 실행한다.
  2. 비대화 모드에서는 `--install-uv`를 줄 때만 설치한다.
- 틀리면: 회사 정책상 허락 없는 도구 설치가 금지된 컴퓨터에서 문제가 될 수 있다.
- 추천: 묻고 설치. 묻지 않으면 사용자가 명령을 하나 더 실행해야 해서 성공 기준을 놓친다.
- 옵션1: 묻고 설치한다.
- 옵션2: 설치하지 않고 설치 명령 한 줄을 안내한 뒤 멈춘다. uv가 없는 사용자는 명령이 2개가 된다.

### 질문4. Claude Code가 실행 중이면 설치를 멈출까?

- 배경: 설치는 Claude Code가 실행 중에도 쓰는 `$HOME/.claude.json`을 고친다. 두 쓰기가 겹치면 한쪽 변경이 사라진다.
- 바뀌는 것:
  1. 대화 모드는 종료할 때까지 기다린다.
  2. 비대화 모드는 exit 3으로 끝난다.
  3. 확인을 건너뛰는 옵션은 없다.
- 틀리면: IDE나 데스크톱 앱의 Claude Code를 감지하지 못해, 실행 중인데도 설치가 진행될 수 있다.
- 추천: 멈춘다. 변경이 사라지면 사용자는 원인을 알 수 없다.
- 옵션1: 멈춘다.
- 옵션2: 경고만 하고 진행한다. 설치 명령은 짧아지지만 MCP 등록이 사라질 수 있다.

### 질문5. Vault 이름 없이 `link`를 실행하면 어떤 Vault를 연결할까?

- 배경: 사람은 저장소 하나를 명령 하나로 연결하길 원했다. project Vault는 한 저장소 전용이고, personal과 team은 여러 저장소가 함께 쓴다. 새 역할이 나중에 생길 수 있다.
- 바뀌는 것:
  1. `vault-builder link --repo <경로>`가 project가 아닌 모든 Vault를 연결한다.
  2. 역할 목록에 없는 새 역할의 Vault도 함께 연결한다.
- 틀리면: 한 저장소용으로 만든 새 역할 Vault가 다른 저장소 세션의 검색에 보인다.
- 추천: 목록에 없는 역할도 공유로 본다. 새 역할을 추가할 때 코드나 사용법을 바꾸지 않아도 된다.
- 옵션1: 추천대로 한다.
- 옵션2: 목록에서 공유로 표시된 역할만 연결한다. 새 역할은 `roles.py`에 한 줄을 더하거나 이름을 적어 연결해야 한다.

### 질문6. 질문 없이 설치할 때 project Vault를 어디에 만들까?

- 배경: 기준 사용자는 앱 저장소 하나와 그 저장소용 project Vault 하나를 쓴다. 지금 project Vault 위치에 관한 관례가 없다.
- 바뀌는 것:
  1. `--repo /path/app`만 주면 `$HOME/vaults/app`에 project Vault `app`이 생긴다.
  2. 개인 Vault는 `$HOME/vault`에 생긴다.
- 틀리면: 같은 경로에 다른 폴더가 있으면 설치가 멈춘다. 사용자가 기대한 위치와 다를 수 있다.
- 추천: `$HOME/vaults/<저장소 폴더 이름>`. Vault가 늘어도 한 폴더에 모인다.
- 옵션1: 추천대로 한다.
- 옵션2: 저장소 옆 `<저장소 경로>-vault`. 저장소와 가깝지만 저장소 부모 폴더에 쓰기 권한이 필요하다.
