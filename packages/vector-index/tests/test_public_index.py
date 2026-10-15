import pytest

from vector_index import IndexedItem, IndexedVector, IndexItem, VectorIndexError, plan_index


def test_partial_changes_keep_unmentioned_items_and_snapshot_deletes_them() -> None:
    current = (
        IndexedItem("notes", "a", "a-v1", "model-v1", "old"),
        IndexedItem("notes", "b", "b-v1", "model-v1", "same"),
    )
    items = (IndexItem("notes", "a", "a-v1", "new text", "new"),)
    changes = plan_index(items, current, collection_ids=("notes",), input_kind="changes", space_id="model-v1")
    assert tuple(row.record_id for row in changes.deletions) == ("a-v1",)
    snapshot = plan_index(items, current, collection_ids=("notes",), input_kind="snapshot", space_id="model-v1")
    assert tuple(row.record_id for row in snapshot.deletions) == ("a-v1", "b-v1")


def test_out_of_scope_manifest_is_rejected_before_deletion() -> None:
    with pytest.raises(VectorIndexError, match="outside"):
        plan_index(
            (),
            (IndexedItem("other", "a", "a-v1", "model-v1", "old"),),
            collection_ids=("notes",),
            input_kind="snapshot",
            space_id="model-v1",
        )


def test_model_change_deletes_previous_space_only_for_changed_items() -> None:
    current = (
        IndexedItem("notes", "a", "a-v1", "model-v1", "same"),
        IndexedItem("notes", "b", "b-v1", "model-v1", "same"),
    )
    plan = plan_index(
        (IndexItem("notes", "a", "a-v2", "a", "same"),),
        current,
        collection_ids=("notes",),
        input_kind="changes",
        space_id="model-v2",
    )
    assert tuple(row.record_id for row in plan.deletions) == ("a-v1",)
    assert plan.upserts[0].record_id == "a-v2"


def test_empty_snapshot_clears_only_declared_logical_collection() -> None:
    current = (IndexedItem("notes", "a", "a-v1", "model-v1", "same"),)
    plan = plan_index((), current, collection_ids=("notes",), input_kind="snapshot", space_id="model-v1")
    assert plan.deletions == current
    assert plan.upserts == ()


def test_changed_model_can_reuse_a_record_id_in_a_new_physical_space() -> None:
    current = (IndexedItem("notes", "a", "a", "v1", "same"), IndexedItem("notes", "a", "a", "v2", "same"))
    plan = plan_index(
        (IndexItem("notes", "a", "a", "a", "same"),),
        current,
        collection_ids=("notes",),
        input_kind="snapshot",
        space_id="v2",
    )
    assert plan.deletions == (current[0],)
    assert plan.unchanged_count == 1


def test_batch_output_failure_cannot_mutate_storage_and_retry_succeeds() -> None:
    from text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector

    from vector_index import VectorIndex

    spec = EmbeddingModelSpec("fixture", "v1", 2, "v1")

    class Provider:
        fail = True

        def model_spec(self) -> EmbeddingModelSpec:
            return spec

        def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
            if self.fail:
                return ()
            return tuple(EmbeddingVector(row.input_id, (1.0, 0.0), spec) for row in inputs)

    class Store:
        def __init__(self) -> None:
            self.writes: list[tuple[tuple[IndexedVector, ...], tuple[IndexedItem, ...]]] = []

        def manifest(self, collection_ids: tuple[str, ...]) -> tuple[IndexedItem, ...]:
            return ()

        def apply(self, records: tuple[IndexedVector, ...], deletions: tuple[IndexedItem, ...]) -> None:
            self.writes.append((records, deletions))

    store = Store()
    provider = Provider()
    index = VectorIndex(store, provider, batch_size=1)
    plan = index.plan((IndexItem("notes", "a", "a-v1", "a", "a"),), collection_ids=("notes",), input_kind="snapshot")
    with pytest.raises(VectorIndexError, match="output IDs"):
        index.apply(plan)
    assert store.writes == []
    provider.fail = False
    index.apply(plan)
    assert len(store.writes) == 1
    assert store.writes[0][0][0].values == (1.0, 0.0)


def test_preprocessing_contract_changes_vector_space() -> None:
    from text_embeddings import EmbeddingModelSpec

    from vector_index import model_space_id

    spec = EmbeddingModelSpec("fixture", "v1", 2, "v1")
    assert model_space_id(spec, preprocessing_id="plain") != model_space_id(spec, preprocessing_id="with-title")


def test_public_embed_rejects_duplicate_items_across_batches() -> None:
    from text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector

    from vector_index import embed_items

    class Provider:
        def model_spec(self) -> EmbeddingModelSpec:
            return EmbeddingModelSpec("fixture", "v1", 2, "v1")

        def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
            return tuple(EmbeddingVector(row.input_id, (1.0, 0.0), self.model_spec()) for row in inputs)

    item = IndexItem("notes", "a", "a-v1", "a", "a")
    with pytest.raises(VectorIndexError, match="duplicate"):
        embed_items((item, item), Provider(), batch_size=1)


@pytest.mark.parametrize("with_submitted_item", [False, True])
def test_direct_plan_cannot_delete_without_a_valid_update(with_submitted_item: bool) -> None:
    from text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector

    from vector_index import IndexPlan, VectorIndex, model_space_id

    spec = EmbeddingModelSpec("fixture", "v1", 2, "v1")

    class Provider:
        def model_spec(self) -> EmbeddingModelSpec:
            return spec

        def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
            raise AssertionError("invalid plans must fail before embedding")

    class Store:
        def manifest(self, collection_ids: tuple[str, ...]) -> tuple[IndexedItem, ...]:
            return ()

        def apply(self, records: tuple[IndexedVector, ...], deletions: tuple[IndexedItem, ...]) -> None:
            raise AssertionError("invalid plans must fail before storage")

    row = IndexedItem("notes", "a", "a", model_space_id(spec), "same")
    items = (IndexItem("notes", "a", "new-id", "changed", "new"),) if with_submitted_item else ()
    plan = IndexPlan(("notes",), model_space_id(spec), "changes", items, (), (row,), 0)
    with pytest.raises(VectorIndexError, match="invalid or stale"):
        VectorIndex(Store(), Provider()).apply(plan)


def test_nonfinite_output_is_rejected_before_storage() -> None:
    from text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector

    from vector_index import VectorIndex

    spec = EmbeddingModelSpec("fixture", "v1", 2, "v1")

    class Provider:
        def model_spec(self) -> EmbeddingModelSpec:
            return spec

        def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
            return tuple(EmbeddingVector(row.input_id, (float("nan"), 1.0), spec) for row in inputs)

    class Store:
        def manifest(self, collection_ids: tuple[str, ...]) -> tuple[IndexedItem, ...]:
            return ()

        def apply(self, records: tuple[IndexedVector, ...], deletions: tuple[IndexedItem, ...]) -> None:
            raise AssertionError("invalid vectors must fail before storage")

    index = VectorIndex(Store(), Provider())
    plan = index.plan((IndexItem("notes", "a", "a", "a", "a"),), collection_ids=("notes",), input_kind="snapshot")
    with pytest.raises(VectorIndexError, match="finite"):
        index.apply(plan)


def test_backend_partial_failure_is_replanned_and_retried() -> None:
    from text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector

    from vector_index import VectorIndex

    spec = EmbeddingModelSpec("fixture", "v1", 2, "v1")

    class Provider:
        def model_spec(self) -> EmbeddingModelSpec:
            return spec

        def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
            return tuple(EmbeddingVector(row.input_id, (1.0, 0.0), spec) for row in inputs)

    class Store:
        def __init__(self) -> None:
            self.rows: dict[str, IndexedItem] = {}
            self.fail = True

        def manifest(self, collection_ids: tuple[str, ...]) -> tuple[IndexedItem, ...]:
            return tuple(row for row in self.rows.values() if row.collection_id in collection_ids)

        def apply(self, records: tuple[IndexedVector, ...], deletions: tuple[IndexedItem, ...]) -> None:
            for row in deletions:
                self.rows.pop(row.record_id, None)
            for vector in records:
                self.rows[vector.item.record_id] = vector.item
                if self.fail:
                    self.fail = False
                    raise OSError("injected partial write")

    store = Store()
    index = VectorIndex(store, Provider())
    items = (IndexItem("notes", "a", "a", "a", "a"), IndexItem("notes", "b", "b", "b", "b"))
    plan = index.plan(items, collection_ids=("notes",), input_kind="snapshot")
    with pytest.raises(OSError, match="partial write"):
        index.apply(plan)
    assert set(store.rows) == {"a"}
    retry = index.plan(items, collection_ids=("notes",), input_kind="snapshot")
    assert retry.unchanged_count == 1
    index.apply(retry)
    assert set(store.rows) == {"a", "b"}
    assert index.plan((), collection_ids=("notes",), input_kind="changes").deletions == ()
