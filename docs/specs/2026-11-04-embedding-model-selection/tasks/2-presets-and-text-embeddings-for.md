## id

2

## title

Add the preset table, `text_embeddings_for`, and the query and document prefixes, and switch all five places that create the config

## goal

The user's model choice decides which model all index and search paths use. arctic-l becomes the default, and adding a model means adding one table entry. This serves Intent 2 and Intent 6, and the model-specific prefixes that Intent 2 needs for quality.

## files

- `src/vault_graph/interface/composition/adapters/text_embeddings.py`
- `src/vault_graph/storage/interfaces/text_embeddings.py`
- `src/vault_graph/operation/scope/catalog_service.py`
- `src/vault_graph/retrieval/search/retrieval_service.py`
- `src/vault_graph/interface/cli/main.py` (only the `_text_embeddings` functions at :306 and :311)
- `src/vault_graph/interface/composition/local_index_service_factory.py` (only :237 and :339)
- `src/vault_graph/interface/composition/read_only_service_factory.py`
- `src/vault_graph/interface/composition/recall_index_refresh.py`
- `tests/fakes/deterministic_text_embeddings.py`
- `tests/test_acceptance_success_criteria.py`
- `tests/test_cli_search.py`
- `tests/test_fastembed_text_embeddings.py`
- `tests/test_vector_indexing_read_only_boundary.py`
- `tests/test_retrieval_service_search.py`
- `tests/test_embedding_config_errors.py` (new)

## blockers

- 1

## acceptance

- A-4
- A-5
- A-6
- A-7
- A-11
- A-12
- A-13
- A-14
- A-15
- A-28

## checks

- `uv run --python 3.12 pytest -q tests/test_fastembed_text_embeddings.py tests/test_retrieval_service_search.py tests/test_cli_search.py tests/test_embedding_config_errors.py tests/test_vector_indexing_read_only_boundary.py tests/test_acceptance_success_criteria.py tests/test_read_only_boundary.py tests/test_search_read_only_boundary.py`
- `rg -n 'FastEmbedTextEmbeddingsConfig\(' src` (A-7)
- `rg -n 'llm/models' src` (A-7)
- `uv run --python 3.12 mypy src tests`
- `shasum $HOME/.vault-graph/projections/active.json $HOME/.vault-graph/configs/*`, run before and after the task (A-28)

## done-when

- [ ] The arctic-l and e5-small `revision`, `repo_id`, `model_file` and `files` values are pinned from a Hugging Face API metadata lookup, with no model download. This file records the source URL for each value.
- [ ] `EMBEDDING_PRESETS` has `arctic-l`, `e5-small` and `minilm`, and `DEFAULT_EMBEDDING_PRESET == "arctic-l"`. The three old constants are deleted and no alias is left behind.
- [ ] `FastEmbedTextEmbeddingsConfig` holds `preset`, and `_config_for_local_files_only` uses `dataclasses.replace`.
- [ ] `text_embeddings_for` is the only place that creates the config. All five former call sites call it with the `local_files_only` value given in spec 4.2.
- [ ] `CatalogService` no longer has `embedding_cache_path`, and has `embedding_config_path` and `save_embedding_selection`. `assert_cache_target_safe` checks the model folder from the settings file.
- [ ] `snapshot_download` gets `allow_patterns=preset.files`. Custom presets are registered only once per process, and the MiniLM warning filter applies only to minilm.
- [ ] The `TextEmbeddings` Protocol has `embed_query`. Retrieval calls it, and all three test fakes implement it.
- [ ] When the settings file is bad, the background-index decision writes the error to `<graph-home>/logs` and starts no index run (spec 6).

## 고정 값과 출처 (2026-11-04, Hugging Face API 메타데이터만 조회)

| 프리셋 | revision | 모델 파일 | 출처 |
|---|---|---|---|
| arctic-l | `ac6544c8a46e00af67e330e85a9028c66b8cfd9a` | `onnx/model_int8.onnx` (569,721,975 bytes) | https://huggingface.co/api/models/Snowflake/snowflake-arctic-embed-l-v2.0/revision/main |
| e5-small | `761b726dd34fb83930e26aab4e9ac3899aa1fa78` | `onnx/model_int8.onnx` (118,054,593 bytes) | https://huggingface.co/api/models/Xenova/multilingual-e5-small/revision/main |

두 프리셋 모두 `files`에 모델 파일과 `config.json`, `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`을 둔다. fastembed가 토크나이저를 읽을 때 요구하는 파일이다.
