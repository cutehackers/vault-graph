"""Compatibility import for :mod:`vault_graph.interface.composition.adapters.code_projection_storage`."""

import sys
from pathlib import Path as Path

from vault_graph.interface.composition.adapters import code_projection_storage as _implementation
from vault_graph.interface.composition.adapters.code_projection_storage import (
    open_code_projection_reader as open_code_projection_reader,
)
from vault_graph.interface.composition.adapters.code_projection_storage import (
    open_code_projection_writer as open_code_projection_writer,
)
from vault_graph.project.code.code_models import CODE_PARSER_SPEC_VERSION as CODE_PARSER_SPEC_VERSION
from vault_graph.storage.interfaces.code_projection_store import CodeProjectionStore as CodeProjectionStore
from vault_graph.storage.local.sqlite_code_projection_store import (
    SQLiteCodeProjectionStore as SQLiteCodeProjectionStore,
)

sys.modules[__name__] = _implementation
