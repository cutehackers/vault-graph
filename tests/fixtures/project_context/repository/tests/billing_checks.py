# mypy: ignore-errors
from src.billing import calculate_total


def test_calculate_total() -> None:
    assert calculate_total(10, 2) == 12
