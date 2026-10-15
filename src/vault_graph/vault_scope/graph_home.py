"""Compatibility import for :mod:`vault_graph.operation.scope.graph_home`."""

import hashlib as hashlib
import json as json
import os as os
import sys
import tempfile as tempfile
from collections.abc import Iterable as Iterable
from dataclasses import dataclass as dataclass
from pathlib import Path as Path

from vault_graph.errors import DataHomeManifestError as DataHomeManifestError
from vault_graph.errors import DataHomeNotInitializedError as DataHomeNotInitializedError
from vault_graph.errors import LegacyDataHomeDetectedError as LegacyDataHomeDetectedError
from vault_graph.operation.scope import graph_home as _implementation
from vault_graph.operation.scope.graph_home import DATA_HOME_FORMAT as DATA_HOME_FORMAT
from vault_graph.operation.scope.graph_home import DATA_HOME_LAYOUT_VERSION as DATA_HOME_LAYOUT_VERSION
from vault_graph.operation.scope.graph_home import DEFAULT_GRAPH_HOME as DEFAULT_GRAPH_HOME
from vault_graph.operation.scope.graph_home import MANIFEST_NAME as MANIFEST_NAME
from vault_graph.operation.scope.graph_home import GraphHomeDescriptor as GraphHomeDescriptor
from vault_graph.operation.scope.graph_home import GraphHomeManifest as GraphHomeManifest
from vault_graph.operation.scope.graph_home import GraphHomeResolver as GraphHomeResolver
from vault_graph.operation.scope.graph_home import _existing_path_chain as _existing_path_chain
from vault_graph.operation.scope.graph_home import _legacy_data_home_error as _legacy_data_home_error
from vault_graph.operation.scope.graph_home import _looks_legacy as _looks_legacy
from vault_graph.operation.scope.graph_home import _optional_text as _optional_text
from vault_graph.operation.scope.graph_home import _required_text as _required_text
from vault_graph.operation.scope.graph_home import _validate_active_generation as _validate_active_generation
from vault_graph.operation.scope.graph_home import _write_manifest as _write_manifest
from vault_graph.operation.scope.graph_home import data_home_id_for_root as data_home_id_for_root
from vault_graph.operation.scope.path_guard import assert_graph_home_outside_vaults as assert_graph_home_outside_vaults

sys.modules[__name__] = _implementation
