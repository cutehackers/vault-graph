## id

6

## title

Delete empty old-model collections in `commit_projection` and print the result in `vg index`

## goal

After a successful re-index, the unpublished new generation no longer contains empty collections from the previous model, so they stop being copied from generation to generation. This serves Intent 4.

## files

- `src/vault_graph/interface/composition/local_index_service_factory.py` (`commit_projection` only)
- `src/vault_graph/interface/cli/main.py` (`vg index` output only)
- `tests/test_index_collection_cleanup.py` (new)
- `tests/test_watch_service.py` (only if the fake's `commit_projection` signature has to match)

## blockers

- 2
- 3

## acceptance

- A-23
- A-24
- A-25
- A-26
- A-27

## checks

- `uv run --python 3.12 pytest -q tests/test_index_collection_cleanup.py tests/test_watch_service.py`
- `rg -n 'remove_empty_collections' src`, which should match only `storage/local/vector_store_adapter.py` (definition) and `local_index_service_factory.py` (call)
- `git diff 44dbf86 -- packages/`, which must print nothing

## done-when

- [ ] The cleanup runs right before manifest writing and activation, and only when all of these hold: there is a staged generation, there is a publisher, `report.vector` is a `VectorApplyResult`, and `failed` is `False`. `keep` is set to `report.vector.embedding_spec`.
- [ ] A cleanup failure does not stop publishing. `commit_projection` returns the deleted names and the failure message.
- [ ] `vg index` prints `removed_vector_collections: <count>` or `warning: vector collection cleanup failed: <message>` only when there is something to report, and the exit code does not change.
- [ ] The read paths (search, status, session-start) leave the active generation's collection list unchanged.
