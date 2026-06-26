class VaultGraphError(Exception):
    """Base error for Vault Graph domain failures."""


class CatalogError(VaultGraphError):
    """Raised when Vault catalog configuration is invalid."""


class ReadOnlyBoundaryError(VaultGraphError):
    """Raised when an operation would write to Vault content."""


class MetadataStoreError(VaultGraphError):
    """Raised when derived metadata state cannot be read or written."""


class TextEmbeddingsError(VaultGraphError):
    """Raised when text embeddings contracts are violated."""


class VectorStoreError(VaultGraphError):
    """Raised when vector store contracts are violated."""


class KeywordIndexError(VaultGraphError):
    """Raised when keyword candidate lookup contracts are violated."""


class RetrievalContractError(VaultGraphError):
    """Raised when retrieval result contracts are violated."""


class SearchError(VaultGraphError):
    """Raised when search cannot produce a valid response."""


class ContextPackError(VaultGraphError):
    """Raised when context pack contracts are violated."""


class AnswerError(VaultGraphError):
    """Raised when answer planning, composition, or validation cannot safely complete."""


class McpConfigError(VaultGraphError):
    """Raised when explicit MCP config rendering or registration cannot complete."""


class SetupError(VaultGraphError):
    """Raised when one-command setup cannot proceed safely."""


class ResultExplanationError(VaultGraphError):
    """Raised when result explanation contracts are violated or unavailable."""


class MemoryProjectionError(VaultGraphError):
    """Raised when read-only memory projections cannot be assembled safely."""


class GraphStoreError(VaultGraphError):
    """Raised when graph store contracts are violated."""


class GraphStoreUnavailable(GraphStoreError):
    """Raised when graph state cannot be opened or queried."""


class GraphSchemaIncompatible(GraphStoreError):
    """Raised when graph state has an incompatible schema."""


class GraphReadOnlyViolation(GraphStoreError):
    """Raised when a graph write is attempted through a read-only store."""


class GraphRecordInvalid(GraphStoreError):
    """Raised when a graph record violates the public graph contract."""


class GraphIndexingError(VaultGraphError):
    """Raised when graph indexing cannot complete."""


class GraphExtractionError(GraphIndexingError):
    """Raised when deterministic graph extraction produces invalid data."""


class GraphReconcileError(GraphIndexingError):
    """Raised when desired graph state cannot be reconciled with current state."""


class UnsupportedGraphScopeWidthError(GraphIndexingError):
    """Raised when graph indexing is requested for content-scope-limited paths."""
