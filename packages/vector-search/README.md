# nolemy-vector-search

A local, domain-neutral vector store. Install `nolemy-vector-search[chroma]` to write with Chroma. Read-only search and manifest export use SQLite directly without importing Chroma or modifying store files.

Collections supply their own names, dimensions, vector space, and scalar metadata. Callers own embedding generation and any domain-specific filtering. Chroma writes and the SQLite vector payload update are sequential, not one atomic transaction.
