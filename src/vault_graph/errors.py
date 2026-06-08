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


class RetrievalContractError(VaultGraphError):
    """Raised when retrieval result contracts are violated."""
