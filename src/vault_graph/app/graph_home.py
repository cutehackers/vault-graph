"""Compatibility import for :mod:`vault_graph.operation.scope.graph_home`."""

import sys

from vault_graph.operation.scope import graph_home as _implementation
from vault_graph.operation.scope.graph_home import DATA_HOME_FORMAT as DATA_HOME_FORMAT
from vault_graph.operation.scope.graph_home import DATA_HOME_LAYOUT_VERSION as DATA_HOME_LAYOUT_VERSION
from vault_graph.operation.scope.graph_home import DEFAULT_GRAPH_HOME as DEFAULT_GRAPH_HOME
from vault_graph.operation.scope.graph_home import MANIFEST_NAME as MANIFEST_NAME
from vault_graph.operation.scope.graph_home import GraphHomeDescriptor as GraphHomeDescriptor
from vault_graph.operation.scope.graph_home import GraphHomeManifest as GraphHomeManifest
from vault_graph.operation.scope.graph_home import GraphHomeResolver as GraphHomeResolver
from vault_graph.operation.scope.graph_home import data_home_id_for_root as data_home_id_for_root

sys.modules[__name__] = _implementation
