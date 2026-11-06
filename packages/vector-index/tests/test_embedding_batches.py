import pytest
from text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector

from vector_index import IndexItem, VectorIndexError, embed_items
from vector_index.indexing import (
    DEFAULT_MAX_BATCH_ITEMS,
    DEFAULT_TOKEN_BUDGET,
    estimate_tokens_from_bytes,
    iter_embedding_batches,
)


class Provider:
    def __init__(self) -> None:
        self.calls: list[tuple[EmbeddingInput, ...]] = []

    def model_spec(self) -> EmbeddingModelSpec:
        return EmbeddingModelSpec("fixture", "v1", 2, "v1")

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        self.calls.append(inputs)
        return tuple(EmbeddingVector(row.input_id, (float(len(row.text)), 1.0), self.model_spec()) for row in inputs)


def item(item_id: str, text: str) -> IndexItem:
    return IndexItem("notes", item_id, f"{item_id}-v1", text, f"fp-{item_id}")


def test_defaults_follow_the_spec() -> None:
    assert DEFAULT_TOKEN_BUDGET == 8_192
    assert DEFAULT_MAX_BATCH_ITEMS == 256


def test_byte_estimate_is_utf8_bytes_divided_by_three_and_at_least_one() -> None:
    assert estimate_tokens_from_bytes("") == 1
    assert estimate_tokens_from_bytes("abc") == 1
    assert estimate_tokens_from_bytes("abcd") == 2
    # Each Hangul syllable is three UTF-8 bytes.
    assert estimate_tokens_from_bytes("가나다") == 3


def test_every_batch_keeps_count_times_max_tokens_within_budget_and_item_cap() -> None:
    texts = [("x" * (3 * size)) for size in (1, 50, 7, 300, 2, 2, 90, 120, 5, 33, 1, 64)]
    items = tuple(item(f"i{index}", text) for index, text in enumerate(texts))
    provider = Provider()

    batches = list(iter_embedding_batches(items, provider, token_budget=300, max_batch_items=3))

    assert sum(len(batch.items) for batch in batches) == len(items)
    assert {row.item_id for batch in batches for row in batch.items} == {row.item_id for row in items}
    for batch in batches:
        assert 1 <= len(batch.items) <= 3
        assert len(batch.items) * batch.max_estimated_tokens <= 300
        assert batch.max_estimated_tokens == max(estimate_tokens_from_bytes(row.text) for row in batch.items)
        assert len(batch.vectors) == len(batch.items)
    # One provider call per yielded batch.
    assert len(provider.calls) == len(batches)


def test_batches_are_sorted_by_estimated_tokens() -> None:
    items = (item("long", "x" * 300), item("short", "x" * 3), item("mid", "x" * 30))
    batches = list(iter_embedding_batches(items, Provider(), token_budget=10_000, max_batch_items=1))

    assert [batch.items[0].item_id for batch in batches] == ["short", "mid", "long"]


def test_single_item_above_budget_is_embedded_alone() -> None:
    items = (item("small", "x" * 3), item("huge", "x" * 3000))
    batches = list(iter_embedding_batches(items, Provider(), token_budget=100, max_batch_items=10))

    assert [[row.item_id for row in batch.items] for batch in batches] == [["small"], ["huge"]]


def test_vectors_are_bound_to_their_items() -> None:
    items = (item("a", "aaaaaa"), item("b", "b"))
    batches = list(iter_embedding_batches(items, Provider(), token_budget=100, max_batch_items=10))

    pairs = {
        row.item_id: vector.values[0]
        for batch in batches
        for row, vector in zip(batch.items, batch.vectors, strict=True)
    }
    assert pairs == {"a": 6.0, "b": 1.0}


def test_custom_token_estimate_is_used() -> None:
    items = tuple(item(f"i{index}", "x") for index in range(4))
    batches = list(
        iter_embedding_batches(items, Provider(), token_budget=20, max_batch_items=10, estimate_tokens=lambda _: 10)
    )

    assert [len(batch.items) for batch in batches] == [2, 2]


def test_duplicate_items_fail_before_any_embedding() -> None:
    provider = Provider()
    duplicate = item("a", "a")
    with pytest.raises(VectorIndexError, match="duplicate"):
        list(
            iter_embedding_batches((item("b", "b"), duplicate, duplicate), provider, token_budget=1, max_batch_items=1)
        )
    assert provider.calls == []


@pytest.mark.parametrize(("token_budget", "max_batch_items"), [(0, 1), (1, 0), (-1, 1)])
def test_limits_must_be_positive(token_budget: int, max_batch_items: int) -> None:
    with pytest.raises(VectorIndexError, match="positive"):
        list(iter_embedding_batches((), Provider(), token_budget=token_budget, max_batch_items=max_batch_items))


def test_embed_items_collects_the_batches_and_batch_size_alone_still_works() -> None:
    items = tuple(item(f"i{index}", "x" * (index + 1)) for index in range(5))
    provider = Provider()

    vectors = embed_items(items, provider, batch_size=2)

    assert set(vectors) == {("notes", row.item_id) for row in items}
    assert vectors[("notes", "i4")].values == (5.0, 1.0)
    assert all(len(call) <= 2 for call in provider.calls)


def test_embed_items_honors_token_budget() -> None:
    items = tuple(item(f"i{index}", "x" * 30) for index in range(4))
    provider = Provider()

    embed_items(items, provider, batch_size=10, token_budget=20)

    assert [len(call) for call in provider.calls] == [2, 2]
