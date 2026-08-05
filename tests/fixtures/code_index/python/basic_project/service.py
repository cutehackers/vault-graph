"""A small Python fixture for structural extraction."""

from typing import Any


class Base:
    """Fixture base class used to exercise Python inheritance extraction."""


class Service(Base):
    """A service with a property and method."""

    @property
    def name(self) -> str:
        return "service"

    def run(self, value: Any) -> str:
        return helper(value)


def helper(value: str) -> str:
    return value.strip()


def make_service() -> Service:
    return Service()
