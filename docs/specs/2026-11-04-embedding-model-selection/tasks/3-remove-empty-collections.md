## id

3

## title

Add `remove_empty_collections` to the vault_graph Chroma adapter

## goal

There is a safe way to delete only the empty `vault_graph_` collections left behind by old models, without changing the general packages. This serves Intent 4 (old collections do not pile up).

## files

- `src/vault_graph/storage/local/vector_store_adapter.py`
- `tests/test_vector_collection_cleanup.py` (new)

## blockers

none

## acceptance

- A-16
- A-20
- A-21
- A-22

## checks

- `uv run --python 3.12 pytest -q tests/test_vector_collection_cleanup.py tests/test_chroma_vector_store.py tests/test_vector_store_contract.py`
- `git diff 44dbf86 -- packages/`, which must print nothing
- `uv run --python 3.12 mypy src/vault_graph/storage/local/vector_store_adapter.py tests/test_vector_collection_cleanup.py`

## done-when

- [ ] The method imports `chromadb.PersistentClient` lazily, inside the method.
- [ ] It deletes only collections that meet all three conditions: the name has the prefix, the name is not the `keep` collection, and the record count is 0. It returns the deleted names.
- [ ] On a read-only adapter it raises `VectorStoreError` and deletes nothing.
- [ ] The tests use a real Chroma store in a temp folder and download no model.
- [ ] This file records whether a second `PersistentClient` on the same path works with this repo's chromadb version (spec 7.10). If it fails, the task stops and reports back without changing `packages/`.

## spec 7.10 result

It works with chromadb 1.5.9. `SharedSystemClient` keeps one `System` per path with a reference count (`chromadb/api/shared_system_client.py:15-49`), and `Client.close()` stops that `System` only when the last client closes (`chromadb/api/client.py:590-615`). `test_removes_only_empty_old_prefixed_collections` opens the generic store's client, runs the cleanup through a second client that closes afterwards, and then writes and searches through the generic store again. `packages/` is unchanged.
