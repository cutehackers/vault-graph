#!/usr/bin/env bash
# vault-graph install command.
#
#   curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-graph/main/scripts/install.sh | bash
#
# vault-graph needs vault-builder, so this command installs both. vault-builder does not install vault-graph.
#
# 1. Check git and curl, then run vault-builder setup as a dry run, so a cause vault-builder stops on stops this
#    command before anything is installed. Claude Code must not be running. Then check uv (asks before it
#    installs uv, or --install-uv). Without a terminal and without --yes it stops first, as vault-builder setup
#    would.
# 2. Pick the vault-graph ref: VAULT_GRAPH_REF, else the newest release tag vX.Y.Z of the repository. The release
#    workflow creates a tag only for a commit that passed every check, so main is never installed by default.
# 3. uv tool install --force --python 3.12 git+<repository>@<ref>. vg is <uv tool dir --bin>/vg.
# 4. Run the vault-builder install command with VAULT_GRAPH_BIN=<vg> and every option this script does not use.
#    It installs vault-builder, the Vaults, the hooks (which record this vg), the repository links and the
#    vault-wiki MCP server, then runs vault-builder doctor.
# 5. <vg> setup --agent claude --mcp: index every Vault of the vault map and register the vault-graph MCP server.
#
# --uninstall runs vg mcp unregister --agent claude and uv tool uninstall vault-graph. vault-builder stays.
#
# The whole script is one function called on the last line, so `curl | bash` reads all of it before anything
# runs. Questions are read from /dev/tty because stdin is the script.
set -euo pipefail

VG_REPO="${VAULT_GRAPH_REPO:-https://github.com/cutehackers/vault-graph.git}"
BUILDER_REF="${VAULT_BUILDER_REF:-main}"
BUILDER_INSTALLER_URL="https://raw.githubusercontent.com/cutehackers/vault-builder/${BUILDER_REF}/scripts/install.sh"
UV_INSTALL_COMMAND="curl -LsSf https://astral.sh/uv/install.sh | sh"
# vg needs Python 3.12 or newer, and onnxruntime has no wheels for the newest Python yet. uv would pick the newest
# Python on the machine, so the version is pinned (CI uses 3.12).
VG_PYTHON="3.12"
INTERACTIVE=0

usage() {
  cat <<'EOF'
Usage:
  curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-graph/main/scripts/install.sh | bash
  curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-graph/main/scripts/install.sh | bash -s -- --repo /path/app --yes
  curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-graph/main/scripts/install.sh | bash -s -- --uninstall

Options of this script:
  --install-uv      Install uv without asking when it is missing.
  --uninstall       Remove the vault-graph MCP entry and vg. vault-builder, the Vaults and ~/.vault-graph stay.
Every other option goes to the vault-builder install command, for example --repo PATH,
--vault NAME=PATH, --role NAME=ROLE, --yes, --dry-run. --dry-run installs nothing.

Environment:
  VAULT_GRAPH_REF=vX.Y.Z           vault-graph tag or branch to install. Defaults to the newest release tag.
  VAULT_GRAPH_REPO=url             vault-graph git repository. Defaults to cutehackers/vault-graph on GitHub.
  VAULT_BUILDER_REF=main           vault-builder branch or tag. Defaults to main.
  VAULT_BUILDER_INSTALLER=path     A local copy of the vault-builder install command to run instead of the
                                   one downloaded for VAULT_BUILDER_REF.
EOF
}

print_tool_install_help() {
  local tool="$1"
  echo "Missing required command: ${tool}" >&2
  case "$(uname -s 2>/dev/null || echo unknown)" in
    Darwin)
      if [[ "${tool}" == "git" ]]; then
        echo "  xcode-select --install   (or: brew install git)" >&2
      else
        echo "  brew install ${tool}" >&2
      fi
      ;;
    Linux)
      echo "  sudo apt-get install ${tool}   (Debian, Ubuntu)" >&2
      echo "  sudo dnf install ${tool}       (Fedora, RHEL)" >&2
      ;;
  esac
}

check_tools() {
  local missing=0 tool
  for tool in "$@"; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
      print_tool_install_help "${tool}"
      missing=1
    fi
  done
  if [[ "${missing}" -ne 0 ]]; then
    echo "Install the missing tools, then run this command again. Nothing was written." >&2
    exit 1
  fi
}

# Questions need /dev/tty. --yes or no terminal means non-interactive mode.
detect_interactive() {
  local yes="$1"
  INTERACTIVE=0
  if [[ "${yes}" -eq 0 ]] && (: </dev/tty) 2>/dev/null; then
    INTERACTIVE=1
  fi
}

ask_tty() {
  local question="$1" answer=""
  printf '%s ' "${question}" >/dev/tty
  if ! IFS= read -r answer </dev/tty; then
    return 1
  fi
  printf '%s' "${answer}"
}

install_uv() {
  echo "Installing uv: ${UV_INSTALL_COMMAND}"
  if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
    echo "The uv installer failed. Run it yourself to see why: ${UV_INSTALL_COMMAND}" >&2
    exit 1
  fi
  hash -r
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv was installed but is not on PATH. Open a new terminal, then run this command again." >&2
    exit 1
  fi
}

ensure_uv() {
  local install_uv_flag="$1" answer
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${install_uv_flag}" -eq 1 ]]; then
    install_uv
    return 0
  fi
  if [[ "${INTERACTIVE}" -eq 1 ]]; then
    printf 'uv is not installed. This command uses it to install vault-graph.\n' >/dev/tty
    printf 'The uv install command is: %s\n' "${UV_INSTALL_COMMAND}" >/dev/tty
    answer="$(ask_tty "Install uv now? [Y/n]")" || answer="n"
    case "${answer}" in
      ""|y|Y|yes|YES|Yes)
        install_uv
        return 0
        ;;
    esac
    echo "uv is required. Install it with: ${UV_INSTALL_COMMAND}" >&2
    exit 1
  fi
  echo "uv is required. Install it with: ${UV_INSTALL_COMMAND}" >&2
  echo "Or run this command again with --install-uv to install uv automatically." >&2
  exit 1
}

claude_running() {
  command -v pgrep >/dev/null 2>&1 && pgrep -x claude >/dev/null 2>&1
}

# vault-builder setup and vg setup write ~/.claude.json, which Claude Code rewrites while it runs.
require_claude_closed() {
  while claude_running; do
    if [[ "${INTERACTIVE}" -eq 1 ]]; then
      if ! ask_tty "Claude Code is running. Quit every Claude Code session (terminal, IDE and app), then press Enter." >/dev/null; then
        echo "Claude Code is still running; nothing was changed." >&2
        exit 3
      fi
    else
      echo "Claude Code is running. Quit every Claude Code session (terminal, IDE and app), then run this command again." >&2
      echo "Nothing was changed." >&2
      exit 3
    fi
  done
}

# Prints the ref to install: VAULT_GRAPH_REF, else the newest vX.Y.Z tag of the repository.
choose_ref() {
  local tags newest
  if [[ -n "${VAULT_GRAPH_REF:-}" ]]; then
    echo "${VAULT_GRAPH_REF}"
    return 0
  fi
  if ! tags="$(GIT_TERMINAL_PROMPT=0 git ls-remote --tags --refs "${VG_REPO}" 'refs/tags/v*' </dev/null)"; then
    echo "Cannot read the tags of ${VG_REPO}. Check that this computer can reach GitHub over HTTPS. Nothing was written." >&2
    exit 1
  fi
  newest="$(printf '%s\n' "${tags}" \
    | sed -n 's#^[0-9a-f]*[[:space:]]*refs/tags/v\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)$#\1#p' \
    | sort -t . -k1,1n -k2,2n -k3,3n | tail -n 1)"
  if [[ -z "${newest}" ]]; then
    echo "${VG_REPO} has no release tag vX.Y.Z. Set VAULT_GRAPH_REF to a tag or branch. Nothing was written." >&2
    exit 1
  fi
  echo "v${newest}"
}

# Sets VG.
install_vg() {
  local ref="$1" bin
  local command=(uv tool install --force --python "${VG_PYTHON}" "git+${VG_REPO}@${ref}")
  echo "Installing vault-graph ${ref}: ${command[*]}"
  if ! "${command[@]}"; then
    echo "uv tool install failed. Check that ${ref} exists in ${VG_REPO}, then run this command again." >&2
    exit 1
  fi
  if ! bin="$(uv tool dir --bin)" || [[ -z "${bin}" ]]; then
    echo "uv tool dir --bin failed after installing vault-graph." >&2
    exit 1
  fi
  VG="${bin}/vg"
  if [[ ! -x "${VG}" ]]; then
    echo "uv installed vault-graph, but ${VG} is not an executable file." >&2
    exit 1
  fi
  echo "vg: ${VG}"
}

# Sets BUILDER_INSTALLER to a local copy of the vault-builder install command: VAULT_BUILDER_INSTALLER, else the
# one downloaded for VAULT_BUILDER_REF (removed when this script exits).
BUILDER_INSTALLER=""
fetch_builder_installer() {
  if [[ -n "${VAULT_BUILDER_INSTALLER:-}" ]]; then
    BUILDER_INSTALLER="${VAULT_BUILDER_INSTALLER}"
    return 0
  fi
  BUILDER_INSTALLER="$(mktemp "${TMPDIR:-/tmp}/vault-builder-install.XXXXXX")"
  # shellcheck disable=SC2064 # expand now: the path is fixed for the whole run
  trap "rm -f '${BUILDER_INSTALLER}'" EXIT
  if ! curl -fsSL "${BUILDER_INSTALLER_URL}" -o "${BUILDER_INSTALLER}"; then
    echo "Could not download the vault-builder install command from ${BUILDER_INSTALLER_URL}." >&2
    exit 1
  fi
}

# Runs vault-builder setup as a dry run before anything is installed, so a cause vault-builder would stop on
# (a vault a person must review, settings that are not JSON, a bad option) stops this command first.
# The dry run uses --yes so it asks nothing; the real run asks the questions. Its output shows only on failure.
precheck_vault_builder() {
  local output status=0
  echo "Checking that vault-builder can set up this machine (dry run)."
  output="$(bash "${BUILDER_INSTALLER}" "$@" --yes --dry-run </dev/null 2>&1)" || status=$?
  if [[ "${status}" -ne 0 ]]; then
    printf '%s\n' "${output}" >&2
    echo "The vault-builder check exited ${status}. Nothing of vault-graph was installed." >&2
    echo "Fix the cause shown above, then run this command again." >&2
    exit "${status}"
  fi
}

# Runs the vault-builder install command with the given arguments and VAULT_GRAPH_BIN (empty for a dry run).
run_vault_builder() {
  local vg="$1" status=0
  shift
  echo "Running the vault-builder install command (${VAULT_BUILDER_INSTALLER:-${BUILDER_INSTALLER_URL}})"
  if [[ -n "${vg}" ]]; then
    VAULT_GRAPH_BIN="${vg}" bash "${BUILDER_INSTALLER}" "$@" </dev/null || status=$?
  else
    bash "${BUILDER_INSTALLER}" "$@" </dev/null || status=$?
  fi
  return "${status}"
}

run_uninstall() {
  local vg="" uv_bin="" tools=""
  require_claude_closed
  if command -v uv >/dev/null 2>&1; then
    uv_bin="$(uv tool dir --bin 2>/dev/null || true)"
  fi
  if [[ -n "${uv_bin}" && -x "${uv_bin}/vg" ]]; then
    vg="${uv_bin}/vg"
  elif command -v vg >/dev/null 2>&1; then
    vg="$(command -v vg)"
  fi
  if [[ -n "${vg}" ]]; then
    if ! "${vg}" mcp unregister --agent claude; then
      echo "${vg} mcp unregister --agent claude failed; stopped before uv tool uninstall vault-graph." >&2
      exit 1
    fi
  else
    echo "Note: vg was not found; skipped vg mcp unregister --agent claude."
  fi
  # Read the whole list first: grep -q in a pipe can close it early, and pipefail would then read SIGPIPE as "not installed".
  if command -v uv >/dev/null 2>&1; then
    tools="$(uv tool list 2>/dev/null || true)"
  fi
  if [[ $'\n'"${tools}" == *$'\n'"vault-graph "* ]]; then
    if ! uv tool uninstall vault-graph; then
      echo "uv tool uninstall vault-graph failed." >&2
      exit 1
    fi
  else
    echo "Note: vault-graph is not installed with uv; skipped uv tool uninstall vault-graph."
  fi

  echo
  echo "Kept (delete them yourself if you no longer need them):"
  echo "  vault-graph data: ${HOME}/.vault-graph"
  local models_dir="${HOME}/llm/models" saved_dir=""
  local embedding_settings="${HOME}/.vault-graph/configs/embedding.json"
  if [[ -f "${embedding_settings}" ]] && command -v python3 >/dev/null 2>&1; then
    saved_dir="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("models_dir") or "")' \
      "${embedding_settings}" 2>/dev/null || true)"
    [[ -n "${saved_dir}" ]] && models_dir="${saved_dir}"
  fi
  echo "  embedding model folder: ${models_dir}"
  echo "  vault-builder: the hooks fall back to recall.sh and direct capture. Run vault-builder setup to drop"
  echo "  the removed vg from the hook settings, or remove vault-builder with its install command and --uninstall."
}

main() {
  local install_uv_flag=0 uninstall=0 yes=0 dry_run=0 arg
  local builder_args=()
  for arg in "$@"; do
    case "${arg}" in
      --install-uv) install_uv_flag=1 ;;
      --uninstall) uninstall=1 ;;
      -h|--help)
        usage
        return 0
        ;;
      *)
        case "${arg}" in
          --yes) yes=1 ;;
          --dry-run) dry_run=1 ;;
        esac
        builder_args+=("${arg}")
        ;;
    esac
  done
  detect_interactive "${yes}"

  if [[ "${uninstall}" -eq 1 ]]; then
    for arg in ${builder_args[@]+"${builder_args[@]}"}; do
      if [[ "${arg}" != "--yes" ]]; then
        echo "--uninstall takes no other option than --yes, got ${arg}." >&2
        exit 2
      fi
    done
    run_uninstall
    return 0
  fi

  # vault-builder setup stops without a terminal or --yes. Stop here too, before vg is installed.
  if [[ "${INTERACTIVE}" -eq 0 && "${yes}" -eq 0 && "${dry_run}" -eq 0 ]]; then
    echo "No terminal for questions: give --yes to run without questions, or run this command in a terminal." >&2
    echo "  curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-graph/main/scripts/install.sh | bash -s -- --yes" >&2
    exit 2
  fi

  check_tools git curl
  fetch_builder_installer
  if [[ "${dry_run}" -eq 0 ]]; then
    require_claude_closed
    precheck_vault_builder ${builder_args[@]+"${builder_args[@]}"}
  fi
  ensure_uv "${install_uv_flag}"
  local ref
  ref="$(choose_ref)"
  if [[ "${dry_run}" -eq 1 ]]; then
    echo "Dry run: would install vault-graph ${ref} from ${VG_REPO}, then run vg setup --agent claude --mcp."
    run_vault_builder "" ${builder_args[@]+"${builder_args[@]}"}
    return $?
  fi

  VG=""
  install_vg "${ref}"
  local status=0
  run_vault_builder "${VG}" ${builder_args[@]+"${builder_args[@]}"} || status=$?
  if [[ "${status}" -ne 0 ]]; then
    echo "The vault-builder install command exited ${status}. Fix the cause shown above, then run this command again." >&2
    echo "vg is installed at ${VG}; vg setup did not run." >&2
    return "${status}"
  fi

  echo
  echo "Running ${VG} setup --agent claude --mcp. It indexes every Vault; the first run downloads the embedding"
  echo "model (about 135 MB) and can take several minutes. Do not stop it."
  if ! "${VG}" setup --agent claude --mcp; then
    echo "vg setup failed. Run ${VG} setup --vault-id <id> for the Vault named in its setup_failed: line," >&2
    echo "or run this command again." >&2
    return 1
  fi
  echo
  echo "Restart Claude Code (every terminal, IDE and app session), then run /mcp and check that vault-wiki and"
  echo "vault-graph are listed as connected."
}

main "$@"
