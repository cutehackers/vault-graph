## id

1

## title

Add the M01 embedding settings file module `embedding_selection.py`

## goal

Code can read and write the user's model choice and model folder from `<graph-home>/configs/embedding.json`. Bad files are rejected, and the `~/llm/models` default is defined in one place only. This serves Intent 5 (model folder) and Intent 7 (module rules).

## files

- `src/vault_graph/operation/scope/embedding_selection.py` (new)
- `tests/test_embedding_selection.py` (new)

## blockers

none

## acceptance

- A-15 (the `embedding_selection.py` part)
- The format and default-value rules in spec 4.3
- The bad-file and missing-file rows of spec 6

## checks

- `uv run --python 3.12 pytest -q tests/test_embedding_selection.py tests/test_feature_import_direction.py tests/test_module_import_cycles.py tests/test_functional_module_boundaries.py`
- `uv run --python 3.12 ruff check src/vault_graph/operation/scope/embedding_selection.py tests/test_embedding_selection.py`
- `uv run --python 3.12 mypy src/vault_graph/operation/scope/embedding_selection.py tests/test_embedding_selection.py`

## done-when

- [ ] `DEFAULT_MODELS_DIR`, `EmbeddingSelection`, `load_embedding_selection` and `save_embedding_selection` exist, with the signatures in spec 4.3.
- [ ] When the file is missing, `load` returns `model=None` and the default folder, and creates no file.
- [ ] `load` raises an error that names the path in each of these cases: the file is not JSON, `version` is not 1, there is an unknown key, a value has the wrong type, the file is over 4 KiB, or the path is not a regular file.
- [ ] `save` writes a temporary file and then calls `os.replace`.
- [ ] The module imports no other feature area.
