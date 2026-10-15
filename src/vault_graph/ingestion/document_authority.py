"""Compatibility import for :mod:`vault_graph.indexing.ingestion.document_authority`."""

import hashlib as hashlib
import re as re
import sys
from collections.abc import Mapping as Mapping
from dataclasses import replace as replace
from pathlib import PurePosixPath as PurePosixPath
from typing import TYPE_CHECKING as TYPE_CHECKING
from typing import Literal as Literal

from vault_graph.indexing.ingestion import document_authority as _implementation
from vault_graph.indexing.ingestion.document_authority import ALL_DOCUMENT_ROLES as ALL_DOCUMENT_ROLES
from vault_graph.indexing.ingestion.document_authority import DocumentRole as DocumentRole
from vault_graph.indexing.ingestion.document_authority import _family_id as _family_id
from vault_graph.indexing.ingestion.document_authority import _frontmatter_values as _frontmatter_values
from vault_graph.indexing.ingestion.document_authority import _normalize_relation_path as _normalize_relation_path
from vault_graph.indexing.ingestion.document_authority import _provenance_paths as _provenance_paths
from vault_graph.indexing.ingestion.document_authority import assign_provenance_families as assign_provenance_families
from vault_graph.indexing.ingestion.document_authority import classify_document_role as classify_document_role

sys.modules[__name__] = _implementation
