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
