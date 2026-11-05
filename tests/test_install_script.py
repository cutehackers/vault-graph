"""scripts/install.sh: the vault-graph install command.

Every test runs the script with a temporary HOME and a stub PATH (fake uv, vg and pgrep in front of
/usr/bin:/bin). VAULT_GRAPH_REPO is a local git repository with release tags, and VAULT_BUILDER_INSTALLER is a
fake vault-builder install command that logs its arguments and VAULT_GRAPH_BIN. No test reaches the network.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install.sh"
BASH = shutil.which("bash", path="/usr/bin:/bin") or "/bin/bash"
TAGS = ("v0.3.0", "v0.9.1", "v0.10.0", "v1.0.0-rc1", "other")

FAKE_UV = """#!/bin/sh
echo "uv $*" >> "{log}"
bin="$HOME/.local/bin"
case "$1 $2" in
  "tool install") mkdir -p "$bin"; cp "{vg}" "$bin/vg"; chmod 755 "$bin/vg"; exit {install_code} ;;
  "tool dir") echo "$bin"; exit 0 ;;
  "tool list") if [ -x "$bin/vg" ]; then printf 'vault-graph v0.0.0\\n- vg\\n'; fi; exit 0 ;;
  "tool uninstall") rm -f "$bin/vg"; exit 0 ;;
esac
exit 2
"""

FAKE_VG = """#!/bin/sh
echo "vg $*" >> "{log}"
exit 0
"""

FAKE_BUILDER = """#!/bin/sh
echo "vault-builder $* VAULT_GRAPH_BIN=${{VAULT_GRAPH_BIN:-}}" >> "{log}"
exit {code}
"""

FAKE_PGREP = """#!/bin/sh
if [ -e "{flag}" ]; then exit 0; fi
exit 1
"""


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _git(*args: str, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, timeout=60)


class Installer:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.home = tmp / "home"
        self.home.mkdir()
        self.log = tmp / "calls.log"
        self.log.touch()
        self.stub = tmp / "stub"
        self.stub.mkdir()
        self.sources = tmp / "sources"
        self.sources.mkdir()
        self.claude_flag = tmp / "claude-running"
        self.fake_vg = _write(self.sources / "vg", FAKE_VG.format(log=self.log))
        self.set_uv(install_code=0)
        self.set_builder(code=0)
        _write(self.stub / "pgrep", FAKE_PGREP.format(flag=self.claude_flag))
        self.repo = tmp / "vault-graph"
        self.repo.mkdir()
        git_env = {
            "HOME": str(tmp),
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
        _git("init", "-q", "-b", "main", cwd=self.repo, env=git_env)
        _git("commit", "-q", "--allow-empty", "-m", "first", cwd=self.repo, env=git_env)
        for tag in TAGS:
            _git("tag", tag, cwd=self.repo, env=git_env)

    def set_uv(self, *, install_code: int) -> None:
        _write(self.stub / "uv", FAKE_UV.format(log=self.log, vg=self.fake_vg, install_code=install_code))

    def set_builder(self, *, code: int) -> None:
        self.builder = _write(self.sources / "vault-builder-install.sh", FAKE_BUILDER.format(log=self.log, code=code))

    @property
    def vg(self) -> Path:
        return self.home / ".local" / "bin" / "vg"

    def env(self, **extra: str) -> dict[str, str]:
        environment = {
            "HOME": str(self.home),
            "PATH": os.pathsep.join([str(self.stub), "/usr/bin", "/bin"]),
            "TMPDIR": str(self.tmp),
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "VAULT_GRAPH_REPO": str(self.repo),
            "VAULT_BUILDER_INSTALLER": str(self.builder),
        }
        environment.update(extra)
        return environment

    def run(self, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, str(SCRIPT), *args],
            env=self.env(**extra),
            cwd=self.tmp,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            start_new_session=True,
            check=False,
        )

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()


@pytest.fixture
def installer(tmp_path: Path) -> Installer:
    return Installer(tmp_path)


def _ok(result: subprocess.CompletedProcess[str], code: int = 0) -> None:
    assert result.returncode == code, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_installs_the_newest_release_tag_then_vault_builder_then_vg_setup(installer: Installer) -> None:
    result = installer.run("--repo", "/path/app", "--yes")

    _ok(result)
    vg = installer.vg
    assert installer.calls() == [
        f"uv tool install --force --python 3.12 git+{installer.repo}@v0.10.0",
        "uv tool dir --bin",
        f"vault-builder --repo /path/app --yes VAULT_GRAPH_BIN={vg}",
        "vg setup --agent claude --mcp",
    ]
    assert "vault-graph are listed as connected" in result.stdout


def test_vault_graph_ref_chooses_another_tag_or_branch(installer: Installer) -> None:
    _ok(installer.run("--yes", VAULT_GRAPH_REF="main"))

    assert installer.calls()[0] == f"uv tool install --force --python 3.12 git+{installer.repo}@main"


def test_a_repository_without_a_release_tag_stops_before_installing(installer: Installer, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    subprocess.run(["git", "init", "-q", "--bare", str(empty)], check=True, timeout=60)

    result = installer.run("--yes", VAULT_GRAPH_REPO=str(empty))

    _ok(result, 1)
    assert "has no release tag" in result.stderr
    assert installer.calls() == []


def test_dry_run_installs_nothing_and_passes_dry_run_to_vault_builder(installer: Installer) -> None:
    result = installer.run("--yes", "--dry-run")

    _ok(result)
    assert "would install vault-graph v0.10.0" in result.stdout
    assert installer.calls() == ["vault-builder --yes --dry-run VAULT_GRAPH_BIN="]


def test_a_failed_vault_builder_install_skips_vg_setup(installer: Installer) -> None:
    installer.set_builder(code=4)

    result = installer.run("--yes")

    _ok(result, 4)
    assert "vg setup did not run" in result.stderr
    assert not any(call.startswith("vg setup") for call in installer.calls())


def test_a_failed_uv_install_stops_before_vault_builder(installer: Installer) -> None:
    installer.set_uv(install_code=1)

    result = installer.run("--yes")

    _ok(result, 1)
    assert not any(call.startswith("vault-builder") for call in installer.calls())


def test_claude_code_running_exits_3_before_installing(installer: Installer) -> None:
    installer.claude_flag.touch()

    result = installer.run("--yes")

    _ok(result, 3)
    assert installer.calls() == []


def test_missing_uv_without_a_terminal_names_the_install_command(installer: Installer) -> None:
    (installer.stub / "uv").unlink()
    if shutil.which("uv", path="/usr/bin:/bin"):
        pytest.skip("uv is installed in /usr/bin or /bin")

    result = installer.run("--yes")

    _ok(result, 1)
    assert "curl -LsSf https://astral.sh/uv/install.sh | sh" in result.stderr
    assert "--install-uv" in result.stderr


def test_uninstall_unregisters_then_removes_vg_and_keeps_vault_builder(installer: Installer) -> None:
    _ok(installer.run("--yes"))
    installer.log.write_text("", encoding="utf-8")

    result = installer.run("--uninstall")

    _ok(result)
    assert installer.calls() == [
        "uv tool dir --bin",
        "vg mcp unregister --agent claude",
        "uv tool list",
        "uv tool uninstall vault-graph",
    ]
    assert not installer.vg.exists()
    assert f"vault-graph data: {installer.home / '.vault-graph'}" in result.stdout
    assert "vault-builder setup" in result.stdout


def test_uninstall_rejects_other_options(installer: Installer) -> None:
    _ok(installer.run("--uninstall", "--repo", "/x"), 2)


def test_the_script_parses_and_reads_questions_only_from_dev_tty() -> None:
    subprocess.run([BASH, "-n", str(SCRIPT)], check=True, timeout=30)
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.rstrip().splitlines()[-1] == 'main "$@"'
    for line in text.splitlines():
        if re.search(r"\bread -r\b", line) and not line.lstrip().startswith("while "):
            assert "</dev/tty" in line, line
