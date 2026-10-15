"""Compatibility import for :mod:`vault_graph.project.code.code_generation`."""

import json as json
import os as os
import shutil as shutil
import sys
import tempfile as tempfile
import uuid as uuid
from dataclasses import dataclass as dataclass
from pathlib import Path as Path

from vault_graph.errors import VaultGraphError as VaultGraphError
from vault_graph.project.code import code_generation as _implementation
from vault_graph.project.code.code_generation import CodeGenerationError as CodeGenerationError
from vault_graph.project.code.code_generation import CodeGenerationLayout as CodeGenerationLayout
from vault_graph.project.code.code_generation import CodeProjectionGenerationManager as CodeProjectionGenerationManager
from vault_graph.project.code.code_generation import _is_safe_generation_id as _is_safe_generation_id
from vault_graph.project.code.code_generation import _normalize_repository_ids as _normalize_repository_ids
from vault_graph.project.code.code_generation import _required_text as _required_text

sys.modules[__name__] = _implementation
