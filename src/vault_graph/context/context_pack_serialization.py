"""Compatibility import for :mod:`vault_graph.context.pack.context_pack_serialization`."""

import dataclasses as dataclasses
import hashlib as hashlib
import json as json
import math as math
import sys
from dataclasses import replace as replace
from pathlib import Path as Path
from typing import Any as Any

from vault_graph.context.pack import context_pack_serialization as _implementation
from vault_graph.context.pack.context_pack import ContextEvidence as ContextEvidence
from vault_graph.context.pack.context_pack import ContextEvidenceRef as ContextEvidenceRef
from vault_graph.context.pack.context_pack import ContextPack as ContextPack
from vault_graph.context.pack.context_pack import ContextPackActualScope as ContextPackActualScope
from vault_graph.context.pack.context_pack import ContextPackBackend as ContextPackBackend
from vault_graph.context.pack.context_pack import ContextPackBackendUse as ContextPackBackendUse
from vault_graph.context.pack.context_pack import ContextPackBudget as ContextPackBudget
from vault_graph.context.pack.context_pack import ContextPackItem as ContextPackItem
from vault_graph.context.pack.context_pack import ContextPackRequestedScope as ContextPackRequestedScope
from vault_graph.context.pack.context_pack import ContextPackScope as ContextPackScope
from vault_graph.context.pack.context_pack import ContextPackSignal as ContextPackSignal
from vault_graph.context.pack.context_pack import ContextPackStoreRevision as ContextPackStoreRevision
from vault_graph.context.pack.context_pack import ContextPackVault as ContextPackVault
from vault_graph.context.pack.context_pack import ContextPackVaultRevision as ContextPackVaultRevision
from vault_graph.context.pack.context_pack import ContextPackWarning as ContextPackWarning
from vault_graph.context.pack.context_pack_serialization import _to_json_value as _to_json_value
from vault_graph.context.pack.context_pack_serialization import compute_pack_id as compute_pack_id
from vault_graph.context.pack.context_pack_serialization import context_pack_identity_dict as context_pack_identity_dict
from vault_graph.context.pack.context_pack_serialization import context_pack_to_dict as context_pack_to_dict
from vault_graph.context.pack.context_pack_serialization import render_context_pack_json as render_context_pack_json
from vault_graph.context.pack.context_pack_serialization import with_computed_pack_id as with_computed_pack_id
from vault_graph.errors import ContextPackError as ContextPackError

sys.modules[__name__] = _implementation
