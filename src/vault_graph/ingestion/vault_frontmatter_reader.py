"""Compatibility import for :mod:`vault_graph.indexing.ingestion.vault_frontmatter_reader`."""

import hashlib as hashlib
import sys
from dataclasses import dataclass as dataclass
from datetime import date as date
from datetime import datetime as datetime
from typing import Any as Any

import yaml as yaml

from vault_graph.indexing.ingestion import vault_frontmatter_reader as _implementation
from vault_graph.indexing.ingestion.vault_frontmatter_reader import FrontmatterProjection as FrontmatterProjection
from vault_graph.indexing.ingestion.vault_frontmatter_reader import _json_safe_mapping as _json_safe_mapping
from vault_graph.indexing.ingestion.vault_frontmatter_reader import _json_safe_value as _json_safe_value
from vault_graph.indexing.ingestion.vault_frontmatter_reader import read_frontmatter as read_frontmatter

sys.modules[__name__] = _implementation
