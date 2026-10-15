# nolemy-vector-index

Scope-bounded incremental indexing of prepared text items. Import `vector_index`.

`plan_index` is pure. `snapshot` input authorizes removal of absent items only in the declared logical collections. `changes` never removes unmentioned items. Supply current manifests from all model spaces in those logical collections. Physical vector collections and logical input collections are distinct.

`VectorIndex` accepts an embedding provider and an `IndexStore`. It validates all embeddings before storage writes. Storage failure propagates; neither rollback nor concurrent-writer serialization is promised. Use staging or a transactional backend when publication must be atomic.

## Text → index → search

Install `nolemy-vector-index` and `nolemy-vector-search[chroma]`. This example uses a caller-supplied embedding provider with `model_spec()` and `embed()`.

```python
from pathlib import Path
from text_embeddings import EmbeddingInput
from vector_search import ChromaVectorStore
from vector_index import ChromaIndexStore, IndexItem, VectorIndex

store = ChromaVectorStore(Path("./derived-vectors"), initialize=True)
index_store = ChromaIndexStore(store)
index = VectorIndex(index_store, embeddings, preprocessing_id="plain-text-v1")
plan = index.plan(
    (IndexItem("notes", "note-1", "note-1-vector", "Prepared text", "source-revision-1"),),
    collection_ids=("notes",),
    input_kind="snapshot",
)
index.apply(plan)
collection = index_store.collection_spec(plan.space_id, embeddings.model_spec().dimensions)
# Query with a vector produced by the same provider and preprocessing contract.
query_vector = embeddings.embed((EmbeddingInput("query", "Prepared query"),))[0].values
hits = store.search(collection, query_vector, 10,
                    predicate=lambda metadata: metadata["collection_id"] == "notes")
store.close()
```

Logical `collection_ids` are input/deletion partitions, distinct from physical model-space collections. `ChromaIndexStore` discovers all spaces in a selected logical collection, namespaces IDs internally, and preserves user IDs in metadata. Use a dedicated store for this codec. An empty `snapshot` clears selected logical collections; an empty `changes` clears nothing.

Stable `item_id` identifies input across model changes. `record_id` identifies its stored vector within a logical collection. `fingerprint` must cover text and any external preparation policy that affects whether a vector should be replaced. The provider's model specification plus `preprocessing_id` determines vector-space identity. Preparing a plan does not load/download a model. Do not change the provider between plan and apply. Apply rechecks the current manifest and rejects a plan whose computed changes differ; obtain a fresh plan after a write or failure. This is a preflight check, not atomic compare-and-swap or writer locking.

Embedding validation fails before storage mutation. A backend failure may leave partial writes; retry against a fresh manifest or use a private staging store before publication. Concurrent writers require caller coordination. The module does not claim transactions or own source documents.
