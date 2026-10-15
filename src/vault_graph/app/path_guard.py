"""Compatibility import for :mod:`vault_graph.operation.scope.path_guard`."""

import sys

from vault_graph.operation.scope import path_guard as _implementation
from vault_graph.operation.scope.path_guard import assert_graph_home_outside_vaults as assert_graph_home_outside_vaults
from vault_graph.operation.scope.path_guard import (
    assert_graph_home_write_target_allowed as assert_graph_home_write_target_allowed,
)
from vault_graph.operation.scope.path_guard import assert_target_outside_vaults as assert_target_outside_vaults

sys.modules[__name__] = _implementation
