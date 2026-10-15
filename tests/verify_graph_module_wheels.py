"""Install built wheels outside the workspace and exercise their public contracts."""

import hashlib
import json
import subprocess
import sys
import threading
import tomllib
import zipfile
from email.parser import Parser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, unquote, urlparse

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

SEARCH_SMOKE = """
import importlib.util
from graph_search import Edge, GraphLimits, GraphSnapshot, SearchOptions, graph_search
assert importlib.util.find_spec('vault_graph') is None
assert importlib.util.find_spec('graph_document') is None
empty = GraphSnapshot.build(node_ids=(), edges=(), limits=GraphLimits(1, 1, 32, 128))
graph = GraphSnapshot.build(node_ids=('a', 'b'), edges=(Edge('ab', 'a', 'b'),),
                            limits=GraphLimits(2, 1, 32, 128))
result = graph_search(graph, source_id='a', options=SearchOptions('outbound', 1, 2, 1))
assert result.stop_reason == 'completed'
assert [visit.node_id for visit in result.visits] == ['a', 'b']
"""

DOCUMENT_SMOKE = """
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from graph_document import (Document, DocumentFeatures, EvidenceLocation, ExtractionProfile,
    GraphDocument, GraphLimits, ItemQuery, LocatedValue, ReadLimits, MissingSearchDependencyError)
assert importlib.util.find_spec('vault_graph') is None
assert importlib.util.find_spec('graph_search') is None
limits = GraphLimits(10, 10000, 100000, 100, 100, 1000, 1024)
read_limits = ReadLimits(100, 100, 1000, 10, 100000)
document = Document('doc', 'r1', 'Title', 'Alpha',
    DocumentFeatures(tags=(LocatedValue('Alpha', EvidenceLocation('tag1', (0, 5))),)))
with TemporaryDirectory() as directory:
    path = str(Path(directory) / 'derived.sqlite')
    with GraphDocument.open(path, mode='create', limits=limits, profile=ExtractionProfile()) as store:
        update = store.update_documents((document,), collection_id='example', expected_revision=0)
        snapshot = store.read(collection_id='example', selection='all', limits=read_limits)
        assert update.graph_revision == snapshot.graph_revision == 1
    with GraphDocument.open(path, mode='read_only', limits=limits, profile=ExtractionProfile()) as store:
        reopened = store.read(collection_id='example', selection='all', limits=read_limits)
        assert reopened == snapshot
    assert snapshot.find_items(ItemQuery('Alpha')).items
    from graph_document.search_bridge import prepare_search
    try:
        prepare_search(snapshot, graph_limits=None)
    except MissingSearchDependencyError:
        pass
    else:
        raise AssertionError('graph_search must remain optional')
"""

BRIDGE_SMOKE = (
    DOCUMENT_SMOKE.split("assert importlib.util.find_spec('graph_search') is None")[0]
    + """
from graph_document.search_bridge import prepare_search
from graph_search import GraphLimits as SearchLimits, SearchOptions, graph_search
limits = GraphLimits(10, 10000, 100000, 100, 100, 1000, 1024)
read_limits = ReadLimits(100, 100, 1000, 10, 100000)
document = Document('doc', 'r1', 'Title', 'Alpha',
    DocumentFeatures(tags=(LocatedValue('Alpha', EvidenceLocation('tag1', (0, 5))),)))
with TemporaryDirectory() as directory:
    with GraphDocument.open(str(Path(directory) / 'derived.sqlite'), mode='create',
                            limits=limits, profile=ExtractionProfile()) as store:
        store.update_documents((document,), collection_id='example', expected_revision=0)
        snapshot = store.read(collection_id='example', selection='all', limits=read_limits)
bundle = prepare_search(snapshot, graph_limits=SearchLimits(100, 100, 1024, 100000))
assert bundle.read is snapshot
source = next(node.node_id for node in snapshot.nodes if node.kind == 'document')
result = graph_search(bundle.graph, source_id=source, options=SearchOptions('outbound', 1, 100, 100))
assert result.stop_reason == 'completed' and len(result.visits) == 2
path = result.path_to(result.visits[-1].node_id).path
assert path is not None
lookup = bundle.read.evidence_for(edge_ids=tuple(step.edge_id for step in path.steps))
assert lookup.by_edge_id[0][1][0].document_id == 'doc'
"""
)

VAULT_SMOKE = r"""
from vault_graph.app.graph_document_service_factory import GraphDocumentServiceFactory
from vault_graph.projection import VaultGraphProjectionAdapter
from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
from vault_graph.projection.graph_projection import GraphProjectionInput, GraphProjectionNode
node = GraphProjectionNode('v', 'a', 'Concept', 'A', 'a')
request = GraphProjectionInput((node,), (node,), (), ('v:wiki:local',), ('graph-v1',),
                               1, 'both', (), ('stated',), False, 10, 500)
assert VaultGraphProjectionAdapter().project(request) == RustworkxGraphProjection().project(request)
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_store_factory import open_graph_store, write_graph_backend_selection
from vault_graph.extraction.entity_extractor import DeterministicEntityExtractor
from vault_graph.extraction.relationship_extractor import DeterministicRelationshipExtractor
from vault_graph.extraction.graph_source_store import MetadataGraphSourceStore
from vault_graph.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.indexing.graph_indexer import GraphIndexer
from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
with TemporaryDirectory() as directory:
    root = Path(directory)
    vault = root / 'vault'
    (vault / 'wiki').mkdir(parents=True)
    (vault / 'wiki' / 'source.md').write_text('---\ntitle: Source\n---\n# Overview\nSee [[target]].\n')
    (vault / 'wiki' / 'target.md').write_text('# Target\nTarget evidence.\n')
    config = CatalogService(graph_home_path=root / 'state')
    catalog = config.create_default_catalog(vault_root=vault)
    metadata = SQLiteMetadataStore(config.metadata_path, initialize=True)
    scope = catalog.default_scope()
    MetadataIndexer(catalog=catalog, metadata_store=metadata).apply(scope=scope, full=True)
    legacy = SQLiteGraphStore.open_writable(config.graph_path)
    indexed = GraphIndexer(source_store=MetadataGraphSourceStore(metadata), graph_store=legacy,
        entity_extractor=DeterministicEntityExtractor(), relationship_extractor=DeterministicRelationshipExtractor(),
        graph_extraction_spec=current_graph_extraction_spec(), metadata_schema_version=metadata.health().schema_version
    ).apply(requested_scope=scope, actual_scopes=(scope,), full=True)
    assert not indexed.failed, indexed.error
    document = open_graph_store(config, metadata_store=metadata, writable=True, backend='document')
    document.bootstrap_from_legacy(legacy, (scope,))
    document.close()
    write_graph_backend_selection(config, 'document')
    config.graph_path.unlink()
    result = subprocess.run([sys.executable, '-I', '-c', 'from vault_graph.cli.main import app; app()',
        'related', 'Source', '--graph-home', str(config.graph_home_path), '--format', 'json'],
        capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    assert payload['result_count'] > 0 and payload['projection_build_id']
    assert any(item['entity']['canonical_path'] == 'wiki/target.md' for item in payload['items'])
"""


def run(arguments: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Command failed: {arguments}\n{result.stdout}{result.stderr}")


def install_from_local_simple_index(
    *,
    executable: Path,
    wheels: tuple[Path, ...],
    distributions: tuple[tuple[str, str], ...],
    cwd: Path,
) -> None:
    """Resolve one root requirement with local built wheels ahead of PyPI."""
    artifacts = {wheel.name: wheel.read_bytes() for wheel in wheels}
    digests = {name: hashlib.sha256(content).hexdigest() for name, content in artifacts.items()}
    names = {canonicalize_name(name): wheel.name for (name, _), wheel in zip(distributions, wheels, strict=True)}
    requested_projects: list[str] = []
    downloaded: list[tuple[str, str]] = []

    class RepositoryHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._serve(head=False)

        def do_HEAD(self) -> None:
            self._serve(head=True)

        def _serve(self, *, head: bool) -> None:
            path = unquote(urlparse(self.path).path)
            if path.startswith("/simple/") and path.endswith("/"):
                project = canonicalize_name(path.removeprefix("/simple/").removesuffix("/"))
                requested_projects.append(project)
                filename = names.get(project)
                if filename is None:
                    self.send_error(404)
                    return
                href = f"/files/{quote(filename)}#sha256={digests[filename]}"
                body = f'<html><body><a href="{href}">{filename}</a></body></html>'.encode()
                content_type = "text/html"
            elif path.startswith("/files/"):
                filename = path.removeprefix("/files/")
                if filename not in artifacts:
                    self.send_error(404)
                    return
                body = artifacts[filename]
                content_type = "application/octet-stream"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
                if path.startswith("/files/"):
                    downloaded.append((filename, hashlib.sha256(body).hexdigest()))

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), RepositoryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        root_name, root_version = next(row for row in distributions if canonicalize_name(row[0]) == "vault-graph")
        requirement = f"{root_name}=={root_version}"
        without_index = subprocess.run(
            ["uv", "pip", "install", "--quiet", "--no-cache", "--no-index", "--python", str(executable), requirement],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        assert without_index.returncode != 0, "root requirement unexpectedly resolved without an index"
        local_index = f"http://127.0.0.1:{server.server_port}/simple/"
        run(
            [
                "uv",
                "pip",
                "install",
                "--quiet",
                "--no-cache",
                "--index-strategy",
                "first-index",
                "--index",
                local_index,
                "--default-index",
                "https://pypi.org/simple",
                "--python",
                str(executable),
                requirement,
            ],
            cwd=cwd,
        )
        expected = {(wheel.name, digests[wheel.name]) for wheel in wheels}
        assert expected <= set(downloaded), f"built wheel downloads missing: {expected - set(downloaded)}"
        assert set(names) <= set(requested_projects), "not every built distribution was resolved from the local index"
        probe = subprocess.run(
            [
                str(executable),
                "-I",
                "-c",
                "import importlib.metadata as m, json, sys; print(json.dumps({name: "
                "[m.distribution(name).metadata['Name'], m.version(name)] for name in sys.argv[1:]}))",
                *(name for name, _ in distributions),
            ],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        installed = json.loads(probe.stdout)
        assert installed == {name: [name, version] for name, version in distributions}, installed
        print("Root-only dependency resolution used all six SHA256-verified localhost wheel artifacts.")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


TEXT_SMOKE = """
import importlib.util
from text_embeddings import EmbeddingInput, EmbeddingModelSpec, FastEmbedTextEmbeddings
assert importlib.util.find_spec('vault_graph') is None
assert importlib.util.find_spec('fastembed') is None
class Backend:
    def embed(self, documents, **kwargs):
        return [(1.0, 0.0) for _ in documents]
provider = FastEmbedTextEmbeddings(model_spec=EmbeddingModelSpec('fixture', 'v1', 2, 'v1'),
                                  backend_factory=Backend)
assert provider.embed((EmbeddingInput('example', 'Text'),))[0].values == (1.0, 0.0)
"""

VECTOR_SMOKE = """
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from vector_search import ChromaVectorStore, CollectionSpec
assert importlib.util.find_spec('vault_graph') is None
assert importlib.util.find_spec('text_embeddings') is None
assert importlib.util.find_spec('chromadb') is None
with TemporaryDirectory() as directory:
    path = Path(directory) / 'absent'
    store = ChromaVectorStore(path, read_only=True)
    assert store.search(CollectionSpec('vectors_example', 2), (1.0, 0.0), 10) == ()
    assert not path.exists()
"""

INDEX_SMOKE = """
import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from text_embeddings import EmbeddingModelSpec, EmbeddingVector
from vector_search import ChromaVectorStore
from vector_index import ChromaIndexStore, IndexItem, VectorIndex
assert importlib.util.find_spec('vault_graph') is None
assert importlib.util.find_spec('graph_search') is None
assert importlib.util.find_spec('graph_document') is None
class Provider:
    def model_spec(self):
        return EmbeddingModelSpec('fixture', 'v1', 2, 'v1')
    def embed(self, inputs):
        return tuple(EmbeddingVector(item.input_id, (1.0, 0.0), self.model_spec()) for item in inputs)
with TemporaryDirectory() as directory:
    path = Path(directory) / 'vectors'
    store = ChromaVectorStore(path, initialize=True)
    codec = ChromaIndexStore(store)
    index = VectorIndex(codec, Provider())
    items = (IndexItem('notes', 'a', 'a-v1', 'Text', 'r1'),)
    plan = index.plan(items, collection_ids=('notes',), input_kind='snapshot')
    index.apply(plan)
    assert index.plan(items, collection_ids=('notes',), input_kind='snapshot').unchanged_count == 1
    spec = codec.collection_spec(plan.space_id, 2)
    assert store.search(spec, (1.0, 0.0), 1)[0].metadata['item_id'] == 'a'
    store.close()
    def hashes():
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}
    before = hashes()
    reader = ChromaVectorStore(path, read_only=True)
    assert abs(reader.search(spec, (1.0, 0.0), 1)[0].score - 1.0) < 1e-6
    assert hashes() == before
"""


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with TemporaryDirectory(prefix="graph-module-wheels-") as directory:
        temporary = Path(directory)
        wheels = temporary / "dist"
        built: list[Path] = []
        distributions: list[tuple[str, str]] = []
        for directory_name in (
            "packages/graph-search",
            "packages/graph-document",
            ".",
            "packages/text-embeddings",
            "packages/vector-search",
            "packages/vector-index",
        ):
            project = tomllib.loads((root / directory_name / "pyproject.toml").read_text())["project"]
            run(["uv", "build", "--package", project["name"], "--out-dir", str(wheels)], cwd=root)
            wheel = next(wheels.glob(f"{project['name'].replace('-', '_')}-{project['version']}-*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                metadata_path = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
                metadata = Parser().parsestr(archive.read(metadata_path).decode())
                assert metadata["Name"] == project["name"]
                assert metadata["Version"] == project["version"]
                distributions.append((metadata["Name"], metadata["Version"]))
                declared = metadata.get_all("Requires-Dist", [])
                requirements = [Requirement(value) for value in declared]
                for dependency in project.get("dependencies", []):
                    assert Requirement(dependency) in requirements, (dependency, declared)
                for extra, dependencies in project.get("optional-dependencies", {}).items():
                    for dependency in dependencies:
                        expected = Requirement(f"{dependency}; extra == '{extra}'")
                        assert expected in requirements, (str(expected), declared)
            built.append(wheel)
        search_wheel, document_wheel, vault_wheel, text_wheel, vector_wheel, index_wheel = built
        for name, wheel, smoke in (
            ("search", search_wheel, SEARCH_SMOKE),
            ("document", document_wheel, DOCUMENT_SMOKE),
            ("text", text_wheel, TEXT_SMOKE),
            ("vector", vector_wheel, VECTOR_SMOKE),
        ):
            environment = temporary / name
            run(["uv", "venv", "--python", sys.executable, str(environment)])
            executable = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            run(["uv", "pip", "install", "--quiet", "--python", str(executable), str(wheel)])
            run([str(executable), "-I", "-c", smoke], cwd=temporary)
            if name == "document":
                run(["uv", "pip", "install", "--quiet", "--python", str(executable), str(search_wheel)])
                run([str(executable), "-I", "-c", BRIDGE_SMOKE], cwd=temporary)
        environment = temporary / "vector-index"
        run(["uv", "venv", "--python", sys.executable, str(environment)])
        executable = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        run(
            [
                "uv",
                "pip",
                "install",
                "--quiet",
                "--python",
                str(executable),
                str(text_wheel),
                str(vector_wheel),
                str(index_wheel),
                "chromadb>=1.5.9,<2",
            ]
        )
        run([str(executable), "-I", "-c", INDEX_SMOKE], cwd=temporary)
        environment = temporary / "vault"
        run(["uv", "venv", "--python", sys.executable, str(environment)])
        executable = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        install_from_local_simple_index(
            executable=executable,
            wheels=tuple(built),
            distributions=tuple(distributions),
            cwd=temporary,
        )
        run([str(executable), "-I", "-c", VAULT_SMOKE], cwd=temporary)
        entrypoint = environment / ("Scripts/vg.exe" if sys.platform == "win32" else "bin/vg")
        help_result = subprocess.run(
            [str(entrypoint), "--help"],
            cwd=temporary,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Usage:" in help_result.stdout
    print("All independent wheels, graph bridge, vector pipeline, and installed Vault adapters verified.")


if __name__ == "__main__":
    main()
