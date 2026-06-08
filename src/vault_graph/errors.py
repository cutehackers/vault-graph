class VaultGraphError(Exception):
    """Base error for Vault Graph domain failures."""


class CatalogError(VaultGraphError):
    """Raised when Vault catalog configuration is invalid."""


class ReadOnlyBoundaryError(VaultGraphError):
    """Raised when an operation would write to Vault content."""


class MetadataStoreError(VaultGraphError):
    """Raised when derived metadata state cannot be read or written."""
