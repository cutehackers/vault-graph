def same() -> int:
    return 1


def same() -> int:  # type: ignore[no-redef]  # noqa: F811 - intentional duplicate declaration fixture
    return 2
