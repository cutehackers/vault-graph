# ruff: noqa: E401, I001, F401 - intentional multiple-import fixture
import foo, bar as baz  # type: ignore[import-not-found]
from pkg import thing, other  # type: ignore[import-not-found]
