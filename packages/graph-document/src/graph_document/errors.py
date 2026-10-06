from __future__ import annotations


class GraphDocumentError(Exception):
    code = "graph_document_error"


class InvalidDocumentError(GraphDocumentError, ValueError):
    code = "invalid_document"


class InvalidExtractionError(GraphDocumentError, ValueError):
    code = "invalid_extraction"


class CapacityError(GraphDocumentError):
    code = "capacity_exceeded"


class IdentityConflictError(GraphDocumentError):
    code = "identity_conflict"


class SourceRevisionConflictError(GraphDocumentError):
    code = "source_revision_conflict"


class ExtractionResultConflictError(GraphDocumentError):
    code = "extraction_result_conflict"


class ProfileMismatchError(GraphDocumentError):
    code = "profile_mismatch"


class RevisionConflictError(GraphDocumentError):
    code = "revision_conflict"

    def __init__(self, current_revision: int) -> None:
        self.current_revision = current_revision
        super().__init__(f"Current graph revision is {current_revision}")


class UnknownCollectionError(GraphDocumentError):
    code = "unknown_collection"


class UnknownDocumentError(GraphDocumentError):
    code = "unknown_document"


class ReadOnlyStoreError(GraphDocumentError):
    code = "read_only_store"


class ReadOnlyOpenError(GraphDocumentError):
    code = "read_only_open"


class ClosedStoreError(GraphDocumentError):
    code = "closed_store"


class StoreBusyError(GraphDocumentError):
    code = "store_busy"


class SchemaMismatchError(GraphDocumentError):
    code = "schema_mismatch"


class StoreCorruptError(GraphDocumentError):
    code = "store_corrupt"


class StoreWriteError(GraphDocumentError):
    code = "store_write"


class ExtractionFailedError(GraphDocumentError):
    code = "extraction_failed"


class InvalidCursorError(GraphDocumentError, ValueError):
    code = "invalid_cursor"


class MissingSearchDependencyError(GraphDocumentError, ImportError):
    code = "missing_search_dependency"
