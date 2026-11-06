import sys
from pathlib import Path

import pytest

from vault_graph.indexing.publication import tree_clone
from vault_graph.indexing.publication.tree_clone import clone_tree


def _make_source(root: Path) -> Path:
    source = root / "source"
    (source / "metadata").mkdir(parents=True)
    (source / "metadata" / "marker.txt").write_text("old", encoding="utf-8")
    (source / "bundle.json").write_text("{}", encoding="utf-8")
    return source


@pytest.mark.skipif(sys.platform != "darwin", reason="clonefile(2) exists only on macOS")
def test_clone_tree_clones_folder_on_macos(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _make_source(tmp_path)
    target = tmp_path / "target"

    method = clone_tree(source, target)

    assert method == "clone"
    assert (target / "metadata" / "marker.txt").read_text(encoding="utf-8") == "old"
    assert (target / "bundle.json").read_text(encoding="utf-8") == "{}"
    assert capsys.readouterr().err == ""


@pytest.mark.skipif(sys.platform != "darwin", reason="clonefile(2) exists only on macOS")
def test_writing_cloned_file_leaves_source_unchanged(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    target = tmp_path / "target"

    clone_tree(source, target)
    (target / "metadata" / "marker.txt").write_text("new", encoding="utf-8")

    assert (source / "metadata" / "marker.txt").read_text(encoding="utf-8") == "old"


def test_clonefile_failure_falls_back_to_copytree_with_one_warning_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _make_source(tmp_path)
    target = tmp_path / "target"

    def failing_clonefile(source_path: Path, target_path: Path) -> None:
        target_path.mkdir()
        (target_path / "partial").write_text("x", encoding="utf-8")
        raise OSError(45, "Operation not supported")

    monkeypatch.setattr(tree_clone, "_clonefile", failing_clonefile)

    method = clone_tree(source, target)

    assert method == "copy"
    assert (target / "metadata" / "marker.txt").read_text(encoding="utf-8") == "old"
    assert not (target / "partial").exists()
    err_lines = capsys.readouterr().err.splitlines()
    assert len(err_lines) == 1
    assert "clone" in err_lines[0]


def test_other_os_uses_copytree_with_one_warning_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _make_source(tmp_path)
    target = tmp_path / "target"
    monkeypatch.setattr(sys, "platform", "linux")

    method = clone_tree(source, target)

    assert method == "copy"
    assert (target / "metadata" / "marker.txt").read_text(encoding="utf-8") == "old"
    assert len(capsys.readouterr().err.splitlines()) == 1


def test_clone_tree_refuses_existing_target(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    target = tmp_path / "target"
    target.mkdir()

    with pytest.raises(FileExistsError):
        clone_tree(source, target)
