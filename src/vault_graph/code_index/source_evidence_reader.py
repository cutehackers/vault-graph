"""Compatibility import for :mod:`vault_graph.project.code.source_evidence_reader`."""

import hashlib as hashlib
import sys
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from pathlib import PurePosixPath as PurePosixPath
from urllib.parse import quote as quote

from vault_graph.project.code import source_evidence_reader as _implementation
from vault_graph.project.code.code_models import CodeRepositoryEntry as CodeRepositoryEntry
from vault_graph.project.code.code_models import CodeSymbolRecord as CodeSymbolRecord
from vault_graph.project.code.source_evidence_reader import MAX_SOURCE_LINES as MAX_SOURCE_LINES
from vault_graph.project.code.source_evidence_reader import SourceEvidence as SourceEvidence
from vault_graph.project.code.source_evidence_reader import SourceEvidenceReader as SourceEvidenceReader
from vault_graph.project.code.source_evidence_reader import _repository_path as _repository_path
from vault_graph.project.code.source_evidence_reader import _source_uri as _source_uri
from vault_graph.project.code.source_evidence_reader import _validated_relative_path as _validated_relative_path

sys.modules[__name__] = _implementation
