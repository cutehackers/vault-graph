"""Reject a built dist/ that would publish anything other than the bundled vault-graph wheel and sdist."""

import sys
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

MODULES = (
    ("graph-search", "graph_search"),
    ("graph-document", "graph_document"),
    ("text-embeddings", "text_embeddings"),
    ("vector-search", "vector_search"),
    ("vector-index", "vector_index"),
)


def check_files(dist_dir: Path, version: str) -> tuple[list[str], Path | None, Path | None]:
    errors: list[str] = []
    # uv build writes dist/.gitignore; it is never uploaded or attached.
    names = sorted(path.name for path in dist_dir.iterdir() if path.is_file() and path.name != ".gitignore")
    errors.extend(f"unexpected nolemy distribution in dist/: {name}" for name in names if name.startswith("nolemy_"))
    wheels = [name for name in names if name.startswith(f"vault_graph-{version}-") and name.endswith(".whl")]
    sdists = [name for name in names if name == f"vault_graph-{version}.tar.gz"]
    if len(wheels) != 1:
        errors.append(f"expected exactly 1 wheel vault_graph-{version}-*.whl, found {wheels}")
    if len(sdists) != 1:
        errors.append(f"expected exactly 1 sdist vault_graph-{version}.tar.gz, found {sdists}")
    errors.extend(
        f"unexpected file in dist/: {name}"
        for name in names
        if name not in wheels and name not in sdists and not name.startswith("nolemy_")
    )
    wheel = dist_dir / wheels[0] if len(wheels) == 1 else None
    sdist = dist_dir / sdists[0] if len(sdists) == 1 else None
    return errors, wheel, sdist


def check_wheel(wheel: Path) -> list[str]:
    errors: list[str] = []
    with zipfile.ZipFile(wheel) as archive:
        members = set(archive.namelist())
        metadata_paths = [name for name in members if name.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            return [f"{wheel.name}: expected 1 .dist-info/METADATA, found {sorted(metadata_paths)}"]
        metadata = Parser().parsestr(archive.read(metadata_paths[0]).decode())
    if not any(name.startswith("vault_graph/") for name in members):
        errors.append(f"{wheel.name}: missing vault_graph/")
    for _, module in MODULES:
        if f"{module}/__init__.py" not in members:
            errors.append(f"{wheel.name}: missing {module}/__init__.py")
    for value in metadata.get_all("Requires-Dist", []):
        if canonicalize_name(Requirement(value).name).startswith("nolemy-"):
            errors.append(f"{wheel.name}: METADATA has internal requirement Requires-Dist: {value}")
    return errors


def check_sdist(sdist: Path, version: str) -> list[str]:
    with tarfile.open(sdist) as archive:
        members = set(archive.getnames())
    prefix = f"vault_graph-{version}"
    return [
        f"{sdist.name}: missing {prefix}/packages/{directory}/src/{module}/__init__.py"
        for directory, module in MODULES
        if f"{prefix}/packages/{directory}/src/{module}/__init__.py" not in members
    ]


def main(dist_dir: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    version = str(tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"])
    errors, wheel, sdist = check_files(dist_dir, version)
    if wheel is not None:
        errors.extend(check_wheel(wheel))
    if sdist is not None:
        errors.extend(check_sdist(sdist, version))
    if errors:
        raise SystemExit("Release dist check failed:\n" + "\n".join(f"- {error}" for error in errors))
    print(f"Release dist verified: {wheel.name if wheel else ''}, {sdist.name if sdist else ''}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tests/verify_release_dist.py <dist-dir>")
    main(Path(sys.argv[1]))
