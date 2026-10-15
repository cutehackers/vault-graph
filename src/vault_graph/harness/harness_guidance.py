"""Compatibility import for :mod:`vault_graph.operation.integration.harness.harness_guidance`."""

import os as os
import sys
import tempfile as tempfile
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from typing import Literal as Literal

from vault_graph.errors import HarnessGuidanceError as HarnessGuidanceError
from vault_graph.operation.integration.harness import harness_guidance as _implementation
from vault_graph.operation.integration.harness.harness_guidance import (
    HARNESS_GUIDANCE_END_MARKER as HARNESS_GUIDANCE_END_MARKER,
)
from vault_graph.operation.integration.harness.harness_guidance import (
    HARNESS_GUIDANCE_START_MARKER as HARNESS_GUIDANCE_START_MARKER,
)
from vault_graph.operation.integration.harness.harness_guidance import (
    SUPPORTED_INSTRUCTION_FILES as SUPPORTED_INSTRUCTION_FILES,
)
from vault_graph.operation.integration.harness.harness_guidance import HarnessGuidanceReport as HarnessGuidanceReport
from vault_graph.operation.integration.harness.harness_guidance import HarnessGuidanceRequest as HarnessGuidanceRequest
from vault_graph.operation.integration.harness.harness_guidance import HarnessGuidanceService as HarnessGuidanceService
from vault_graph.operation.integration.harness.harness_guidance import HarnessInstructionFile as HarnessInstructionFile
from vault_graph.operation.integration.harness.harness_guidance import (
    _canonical_existing_directory as _canonical_existing_directory,
)
from vault_graph.operation.integration.harness.harness_guidance import (
    _canonical_new_file_path as _canonical_new_file_path,
)
from vault_graph.operation.integration.harness.harness_guidance import _marker_state as _marker_state
from vault_graph.operation.integration.harness.harness_guidance import _read_instruction as _read_instruction
from vault_graph.operation.integration.harness.harness_guidance import (
    _reject_symlink_components as _reject_symlink_components,
)
from vault_graph.operation.integration.harness.harness_guidance import _with_guidance as _with_guidance
from vault_graph.operation.integration.harness.harness_guidance import _without_guidance as _without_guidance
from vault_graph.operation.integration.harness.harness_guidance import _write_atomically as _write_atomically

sys.modules[__name__] = _implementation
