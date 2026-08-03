from typing import Any


def decorator(fn: Any) -> Any:
    return fn


@decorator
def one() -> int:
    return 1
