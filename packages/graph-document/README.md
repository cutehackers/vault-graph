# nolemy-graph-document

A standalone, rebuildable graph of document contributions. The package reads already parsed documents, extracts explicit facts, and stores derived graph state in a separate SQLite database. It never reads or changes the source documents.

```python
from graph_document import (
    Document, DocumentFeatures, EvidenceLocation, ExtractionProfile, GraphDocument,
    GraphLimits, LocatedValue, ReadLimits,
)

limits = GraphLimits(100, 1_000_000, 10_000_000, 100_000, 100_000, 300_000, 1024)
read_limits = ReadLimits(100_000, 100_000, 300_000, 100, 100_000_000)
profile = ExtractionProfile()
document = Document("doc-1", "source-v1", "Example", "Tags: Alpha", DocumentFeatures(
    tags=(LocatedValue("Alpha", EvidenceLocation("tag:1", (6, 11))),)))
with GraphDocument.open("/absolute/path/derived.sqlite", mode="create", limits=limits,
                        profile=profile) as graph:
    result = graph.update_documents((document,), collection_id="example", expected_revision=0)
    snapshot = graph.read(collection_id="example", selection="all", limits=read_limits)
```

`GraphDocument.open` requires an absolute DB path and an existing parent directory. `create` requires an absent DB. Use `read_write` or `read_only` to open an existing DB. All writes use an expected collection revision. Snapshots are immutable copies and remain usable after the handle closes.

Optional graph traversal requires `nolemy-graph-document[search]`. Import `prepare_search` from `graph_document.search_bridge` only when needed.
