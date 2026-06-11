# Phase 3B Local Entity And Relationship Indexing Design

Status: Draft for implementation planning

Date: 2026-06-11

Scope: Phase 3B only

## 1. Purpose

Phase 3B turns current `MetadataStore` evidence chunks into persisted local graph
state.

The deliverable is deterministic entity and relationship indexing through
scope-local graph reconcile. This slice uses the Phase 3A `GraphStore`,
`GraphExtractionSpec`, graph manifest, graph revision, evidence-ref, and
tombstone contracts. It does not change Vault content, does not build runtime
graph projections, and does not make graph signals part of default search.

The user value is operational:

- `vg index` can build graph state from current metadata chunks.
- graph state can be deleted and rebuilt from Vault-derived metadata.
- graph indexing can repair stale entities, stale relationships, stale evidence
  refs, and tombstones inside the selected Vault scope.
- Phase 3C can later expose `vg related`, `vg decision-trace`, and opt-in graph
  search without inventing another persistence model.

## 2. Value Alignment

Phase 3B follows the product contract from `docs/SPEC.md`,
`docs/DESIGN.md`, and `docs/FEATURES.md`.

| Vault Graph value | Phase 3B design rule |
| --- | --- |
| Vault is the source of truth | Extraction reads only Vault-derived metadata chunks and document snapshots. It never edits Vault files. |
| Derived data is rebuildable | Graph records are recomputed from metadata chunks, `GraphExtractionSpec`, and graph manifest state. |
| Evidence over fluency | Every entity and relationship must have at least one `GraphEvidenceRef` resolving to a `MetadataStore` evidence chunk. |
| Local first | The default extractor is deterministic local code. No hosted model, graph service, or LLM is required. |
| Simplicity before scale | Phase 3B extracts only explicit, inspectable signals: document identity, frontmatter, headings, and local links. |
| Multi-vault correctness | Reconcile runs against per-Vault actual scopes. Same names in different Vaults never merge. |

## 3. Scope

### 3.1 In Scope

Phase 3B implements:

- local deterministic `EntityExtractor`
- local deterministic `RelationshipExtractor`
- `GraphIndexer` planning and applying
- graph dry-run planning for `vg index --dry-run`
- graph apply during `vg index`
- graph upsert, tombstone, and revision reporting
- graph status freshness through existing Phase 3A readiness
- `projection_cache_invalidations` keys inside `GraphReconcilePlan`, without
  writing or building a projection cache
- graph indexing tests for read-only behavior, rebuildability, scope-local
  reconcile, and multi-vault identity

### 3.2 Out Of Scope

Phase 3B must not implement:

- LLM-assisted extraction
- general noun-phrase extraction
- graph node embeddings or relationship embeddings
- rustworkx `GraphProjection`
- graph ranking, traversal, or path finding
- `vg related`
- `vg decision-trace`
- `vg search --include-graph`
- `vg ask`
- context packs
- MCP serving
- HTTP serving
- Neo4j
- cross-Vault entity merging
- automatic Vault publication or Vault file mutation

## 4. Core Design Choice

Phase 3B uses a conservative deterministic extractor.

The extractor must prefer fewer, high-confidence graph records over broad but
noisy semantic extraction. This protects Vault Graph's core value: inspectable
context over fluent guesswork.

Required extraction inputs:

- `ChunkSnapshot` text, path, section, anchor, content hash, chunker version,
  and metadata index revision
- `DocumentSnapshot` frontmatter and document identity when available through
  Vault-scoped `GraphSourceStore.resolve_document`
- current selected actual scope
- current `GraphExtractionSpec`

Required extraction signals:

- document/page/source identity from path and frontmatter
- decision identity from path or frontmatter
- heading concepts from Markdown sections
- tag concepts from frontmatter
- explicit Markdown links and Obsidian-style wiki links
- explicit frontmatter relationship fields

Not allowed in deterministic v1:

- creating entities from arbitrary noun phrases
- treating cached excerpts as evidence authority
- inferring cross-Vault equivalence by name
- silently widening default search with graph records

## 5. Package Layout

Use stable domain names, not phase names.

```text
src/vault_graph/
  extraction/
    __init__.py
    entity_extractor.py
    relationship_extractor.py
  indexing/
    graph_indexer.py
  app/
    index_service.py
  cli/
    main.py

tests/
  test_entity_extractor.py
  test_relationship_extractor.py
  test_graph_indexer.py
  test_graph_indexing_read_only_boundary.py
  test_multi_vault_graph_indexing.py
  test_cli_graph_indexing.py
```

Rules:

- `entity_extractor.py` owns entity occurrences only.
- `relationship_extractor.py` owns relationship occurrences only.
- `graph_indexer.py` owns reconcile planning and applying.
- `GraphStore` remains the only graph persistence boundary.
- CLI and app services must not import SQLite graph tables directly.
- Source files and classes must not include roadmap phase labels.

The current Phase 3A default `GraphExtractionSpec` is a placeholder until graph
indexing writes records. Phase 3B implementation should use behavior names such
as `local-deterministic-entity-extractor` and
`local-deterministic-relationship-extractor` for extractor names so graph
lineage does not depend on roadmap labels.
If this changes the current `GraphExtractionSpec` digest, the implementation
must also use a new `spec_version`; same version with different digest remains
incompatible by Phase 3A contract.

## 6. Architecture

Phase 3B extends the existing indexing pipeline after metadata has produced the
current chunk view.

```text
vg index
  -> resolve requested QueryScope
  -> expand to per-Vault actual scopes
  -> MetadataIndexer.apply or preview
  -> VectorIndexer.apply or plan when vector dependencies are configured
  -> GraphIndexer.apply or plan
       -> GraphSourceStore.list_chunks(actual_scope)
       -> GraphSourceStore.resolve_document(vault_id, document_id)
       -> EntityExtractor
       -> RelationshipExtractor
       -> GraphStore.current_manifest(actual_scopes)
       -> GraphReconcilePlan
       -> GraphStore.apply_reconcile_plan(plan)
  -> report metadata, vector, and graph index state
```

`GraphIndexer` depends on interfaces:

- `GraphSourceStore` for chunks and document snapshots
- `GraphStore` for manifest reads and reconcile writes
- `GraphExtractionSpec` for compatibility and staleness
- extractor protocols for deterministic occurrence extraction

It must not depend on:

- `SQLiteGraphStore` internals
- Chroma internals
- rustworkx
- CLI rendering
- Vault filesystem writes

## 7. Indexing Flow

### 7.1 Dry Run

`vg index --dry-run` must plan graph changes without creating graph files,
vector files, model-cache files, projection-cache files, or Vault files.

Dry-run graph flow:

```text
MetadataIndexer.preview(scope)
  -> preview chunks and document snapshots after metadata apply
  -> VectorIndexer.plan(...)
  -> GraphIndexer.plan(source_store=preview_graph_source, graph_store=read_only)
  -> render planned graph upserts, tombstones, stale count, warnings, and spec
```

If the graph store is missing during dry-run, the plan treats the current graph
manifest as empty and reports all desired records as planned upserts. It must
not create the store just to inspect it.

Phase 3B should extend metadata preview so dry-run exposes the same logical
document and chunk view that apply would produce. A dry-run graph source should
satisfy the `GraphSourceStore` protocol below without writing metadata state.

### 7.2 Apply

`vg index` applies in this order:

1. metadata
2. vector projection when configured
3. graph indexing

Graph indexing may run after metadata succeeds even if vector indexing fails,
because graph state depends on metadata chunks, not embeddings. The final exit
code is nonzero if any enabled derived-state step fails. The output must
identify which step failed and which steps were successfully applied.

If metadata fails, graph indexing must not run because it would not have a
trusted current chunk view.

### 7.3 Full Rebuild

`vg index --full` expands graph reconcile inside the selected actual scopes
only. It does not mean global all-vault rebuild unless the user selected
`--all-vaults`.

Full graph rebuild rules:

- desired records are built from all current chunks in the selected actual
  scopes
- current manifest rows in those actual scopes are compared to desired records
- missing or stale records are upserted
- current records absent from desired state are tombstoned
- records outside the selected actual scopes are untouched

### 7.4 Supported Graph Scope Width

Phase 3B graph indexing supports whole selected Vault scopes only:

- active Vault
- one explicit `--vault-id`
- all enabled Vaults with `--all-vaults`

It must not introduce user-facing content-scope-limited graph indexing such as
`wiki/foo` inside a broader `wiki` Vault scope.

Reason: the Phase 3A manifest is keyed by exact `actual_scope`. A broad `wiki`
graph run and a later narrower `wiki/foo` graph run would otherwise have
overlapping records that cannot be repaired safely by exact scope keys alone.
Supporting that properly requires a separate same-or-child overlap manifest
contract.

Phase 3B implementation rule:

- app-layer graph indexing must reject mixed-width content scopes with a clear
  `unsupported_graph_scope_width` error before calling `GraphIndexer`
- metadata and vector indexing may keep their existing scope behavior
- graph records outside the selected exact Vault actual scopes are untouched
- future content-scope graph indexing must add explicit overlap-aware manifest,
  tombstone, and readiness tests before it is enabled

This is a deliberate simplicity boundary, not a permanent product limit.

### 7.5 Incremental Rebuild

The first Phase 3B implementation may compute desired graph state from all
current chunks in each selected actual scope. This is simpler and safer than an
ad hoc changed-path patcher, and the scope remains bounded by the user's
selection.

Future optimization may use changed document sets, but it must preserve the
same `GraphReconcilePlan` contract and pass the same scope-local contract tests.

## 8. Deterministic Extraction Contract

Extraction returns occurrences, not persisted records. `GraphIndexer` turns
occurrences into deduped `EntityRecord`, `RelationshipRecord`, and
`GraphEvidenceRef` values.

### 8.1 GraphSourceStore

`GraphSourceStore` is the read model that graph indexing consumes.

```python
class GraphSourceStore(Protocol):
    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]: ...
    def resolve_document(self, *, vault_id: str, document_id: str) -> DocumentSnapshot | None: ...
```

Implementations:

- a Vault-scoped adapter over `MetadataStore` satisfies this protocol during
  apply.
- `MetadataIndexer.preview` should expose a preview implementation during
  dry-run, containing a Vault-scoped document map and chunk snapshots after the
  planned metadata apply.

Rules:

- extractors depend on `GraphSourceStore`, not on Vault filesystem reads
- document resolution is Vault-scoped even when the current local metadata
  backend uses globally derived document IDs
- an adapter over an unscoped metadata method must assert
  `document.vault_id == requested vault_id` before returning a document
- the preview implementation must not write metadata, vector, graph, cache, or
  Vault files
- `GraphIndexer` uses `GraphSourceStore` for frontmatter and chunk evidence,
  then relies on `GraphStore` only for current graph state

### 8.2 GraphExtractionContext

`GraphExtractionContext` is the read-only context that lets extractors resolve
explicit local links without reading Vault files or depending on global state.

Logical fields and operations:

- `scope: QueryScope`
- `current_document_paths: tuple[str, ...]`
- `resolve_local_document_link(source_path, raw_target) -> DocumentSnapshot | None`
- `source_store: GraphSourceStore`

Rules:

- `GraphIndexer` builds the context from the selected actual scope before
  invoking extractors.
- link resolution is same-Vault only in Phase 3B.
- link resolution returns a document only when the target path is present in the
  selected current document set.
- unresolved links remain visible as concept mentions and warnings.
- extractors must not normalize paths differently from the context resolver.

### 8.3 EntityOccurrence

Logical fields:

- `vault_id`
- `entity_type`
- `name`
- `normalized_name`
- `aliases`
- `canonical_path`
- `evidence_vault_id`
- `document_id`
- `chunk_id`
- `content_hash`
- `section`
- `anchor`
- `path`
- `excerpt`
- `confidence`
- `extraction_method`

Rules:

- occurrences are immutable values
- every occurrence must point to one evidence chunk
- `normalized_name` uses `normalize_entity_name`
- `entity_id` is derived later with `stable_entity_id`
- `canonical_path` is optional and must be Vault-relative when present

### 8.4 RelationshipOccurrence

Logical fields:

- `relationship_type`
- `source_vault_id`
- `source_entity_key`
- `target_vault_id`
- `target_entity_key`
- `evidence_vault_id`
- `document_id`
- `chunk_id`
- `content_hash`
- `section`
- `anchor`
- `path`
- `excerpt`
- `status`
- `confidence`
- `extraction_method`

Rules:

- Phase 3 stores directed relationships.
- Relationship identity is derived later with `stable_relationship_id`.
- `status` must be one of `stated`, `inferred`, `contested`, or `deprecated`.
- Phase 3B deterministic extraction should produce `stated` for explicit links
  and frontmatter relationships.
- `inferred` is allowed only for deterministic local rules with visible
  evidence, not for hidden model guesses.

### 8.5 EntityExtractor Interface

```python
class EntityExtractor(Protocol):
    def extract(
        self,
        *,
        chunk: ChunkSnapshot,
        document: DocumentSnapshot | None,
        context: GraphExtractionContext,
        scope: QueryScope,
        spec: GraphExtractionSpec,
    ) -> tuple[EntityOccurrence, ...]: ...
```

Required behavior:

- create one document-level entity for each chunk's document when enough
  document identity is available
- create heading concept entities for non-empty section headings
- create tag concept entities from frontmatter tags
- create target entities only for resolvable local links whose target document
  is present in the selected metadata chunk set
- create unresolved link text as a `Concept` mention, not as a durable page
  entity
- keep entity extraction deterministic for the same input chunk and document

### 8.6 RelationshipExtractor Interface

```python
class RelationshipExtractor(Protocol):
    def extract(
        self,
        *,
        chunk: ChunkSnapshot,
        document: DocumentSnapshot | None,
        entities: tuple[EntityOccurrence, ...],
        context: GraphExtractionContext,
        scope: QueryScope,
        spec: GraphExtractionSpec,
    ) -> tuple[RelationshipOccurrence, ...]: ...
```

Required behavior:

- create `mentions` relationships from the document entity to heading, tag, and
  unresolved-link concept entities
- create `links_to` relationships from the document entity to resolvable local
  document/page entities
- create explicit frontmatter relationships when fields are present and the
  target can be resolved to an extracted entity
- avoid duplicate relationships for the same source, target, type, and evidence
  chunk

## 9. Entity Extraction Rules

### 9.1 Document-Level Entity

Every current Markdown document with at least one evidence chunk should produce
one document-level entity.

Entity type selection:

| Condition | Entity type |
| --- | --- |
| frontmatter `type` or `kind` is `decision`, or path contains `/decisions/` | `Decision` |
| path starts with `wiki/` | `WikiPage` |
| path starts with `raw/` | `Source` |
| otherwise | `Document` |

Name selection order:

1. frontmatter `title`
2. first Markdown H1 in the first chunk when available
3. basename without `.md`
4. Vault-relative path

Aliases:

- frontmatter `aliases`
- frontmatter `alias`
- link labels pointing to the same resolved document in the selected scope

Confidence: `1.0` when derived from path/frontmatter. Lower confidence is not
needed for document-level identity.

### 9.2 Heading Concept Entity

Each non-empty heading section may produce one `Concept` entity.

Rules:

- normalize whitespace and case for identity
- ignore generic headings such as `overview`, `summary`, `notes`, `todo`,
  `appendix`, and `references` unless they include a more specific suffix
- use the current chunk as evidence
- canonical path is `None`
- confidence is `0.85`

### 9.3 Frontmatter Tag Concept

Frontmatter tags may produce `Concept` entities.

Rules:

- support scalar string tags and list tags
- strip leading `#`
- ignore empty tags
- use the first chunk of the document as evidence
- confidence is `0.8`

Tags are Vault-derived classification hints. They are not durable truth outside
their evidence.

### 9.4 Link Target Entity

Phase 3B supports explicit local Markdown and wiki links.

Supported forms:

- `[label](relative/path.md)`
- `[label](../relative/path.md#anchor)`
- `[[Page]]`
- `[[Page|Label]]`

Rules:

- links are resolved inside the same Vault only
- cross-Vault link syntax is out of scope for Phase 3B
- target document entities are created only when the target path is present in
  the selected current metadata chunk set
- unresolved links become `Concept` entities with the link label or target text
- external URLs are not graph entities in Phase 3B
- link evidence is the source chunk containing the link

This keeps graph indexing useful without creating false document entities from
broken links or out-of-scope files.

## 10. Relationship Extraction Rules

Required relationship rules:

| Signal | Relationship | Source | Target | Status | Confidence |
| --- | --- | --- | --- | --- | --- |
| heading concept | `mentions` | document entity | concept entity | `stated` | `0.85` |
| frontmatter tag | `mentions` | document entity | concept entity | `stated` | `0.8` |
| resolvable local Markdown/wiki link | `links_to` | document entity | target document/page entity | `stated` | `0.95` |
| unresolved local link | `mentions` | document entity | concept entity | `stated` | `0.7` |
| frontmatter `related` | `related_to` | document entity | resolved target entity | `stated` | `0.9` |
| frontmatter `depends_on` | `depends_on` | document entity | resolved target entity | `stated` | `0.9` |
| frontmatter `blocks` | `blocks` | document entity | resolved target entity | `stated` | `0.9` |
| frontmatter `implements` | `implements` | document entity | resolved target entity | `stated` | `0.9` |
| frontmatter `supersedes` | `supersedes` | document entity | resolved target entity | `stated` | `0.9` |
| frontmatter `revisit_when` | `revisit_when` | document entity | concept entity | `stated` | `0.8` |

Natural-language cue extraction, such as parsing "A depends on B" from ordinary
paragraph text, is not required in Phase 3B. It may be added later behind a new
`GraphExtractionSpec` version after tests prove that precision remains high.

## 11. GraphIndexer Contract

`GraphIndexer` is the deep module for Phase 3B. It returns app-level reports
that wrap the Phase 3A store boundary types.

```python
@dataclass(frozen=True)
class GraphIndexPlanReport:
    reconcile_plan: GraphReconcilePlan
    mode: str
    stale_count: int
    warnings: tuple[str, ...]

@dataclass(frozen=True)
class GraphIndexApplyResult:
    reconcile_plan: GraphReconcilePlan | None
    apply_result: GraphApplyResult | None
    mode: str
    stale_count: int
    warnings: tuple[str, ...]
    failed: bool
    error: str | None

class GraphIndexer:
    def plan(
        self,
        *,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        full: bool = False,
    ) -> GraphIndexPlanReport: ...

    def apply(
        self,
        *,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        full: bool = False,
    ) -> GraphIndexApplyResult: ...
```

Constructor dependencies:

- `source_store: GraphSourceStore`
- `graph_store: GraphStore`
- `entity_extractor: EntityExtractor`
- `relationship_extractor: RelationshipExtractor`
- `graph_extraction_spec: GraphExtractionSpec`
- optional clock or revision ID factory for deterministic tests

Rules:

- `plan` reads metadata chunks, document snapshots, and current graph manifest.
- `plan` does not write graph state.
- `apply` calls `plan`, then passes `report.reconcile_plan` to
  `GraphStore.apply_reconcile_plan`.
- `GraphReconcilePlan` remains the store write contract; app-level warnings and
  failed/error fields live in `GraphIndexPlanReport` and
  `GraphIndexApplyResult`.
- `GraphIndexer` must not mutate Vault files.
- `GraphIndexer` must not read SQLite graph tables directly.
- `GraphIndexer` must not build rustworkx projections.

## 12. Reconcile Algorithm

For each selected actual scope:

1. list current chunks with `GraphSourceStore.list_chunks(actual_scope)`
2. resolve document snapshots for those chunks when needed
3. build a Vault-scoped document path index from current documents
4. build a `GraphExtractionContext`
5. run entity extraction
6. run relationship extraction
7. dedupe occurrences into desired entity and relationship records
8. build desired graph evidence refs
9. read current graph manifest for the same exact actual scopes
10. compare desired records to current manifest rows
11. create upserts for missing or stale records
12. create tombstones for manifest records absent from desired state
13. create one `GraphRevision` row per actual scope
14. return one `GraphReconcilePlan`

Comparison keys:

- entity key: `(vault_id, entity_id)`
- relationship key: `(source_vault_id, relationship_id)`
- evidence key: `(owner_kind, owner_vault_id, owner_id, evidence_vault_id,
  document_id, chunk_id, anchor)`
- tombstone key: `(record_kind, record_vault_id, record_id, actual_scope)`

Staleness keys:

- evidence content hashes
- metadata index revision
- parser version
- chunker version
- graph store schema version
- `GraphExtractionSpec` digest
- relationship status
- graph record active/tombstoned status

`graph_index_revision` is lineage and reporting metadata. It must not be used as
a staleness key, or every successful graph run would make unchanged records
appear stale on the next run.

## 13. Deduplication Rules

Entity dedupe:

- merge occurrences with the same `(vault_id, entity_type, normalized_name,
  canonical_path)`
- combine aliases in deterministic sorted order
- combine evidence refs in deterministic sorted order
- use the maximum confidence from merged occurrences
- keep `status="active"` for desired records

Relationship dedupe:

- merge occurrences with the same relationship type, source entity, and target
  entity
- combine evidence refs in deterministic sorted order
- use the maximum confidence from merged occurrences
- choose status by priority: `contested`, `deprecated`, `stated`, `inferred`
- Phase 3B deterministic v1 should normally emit `stated`

Sorting:

- sort chunks by `(vault_id, path, chunk_id)`
- sort entities by `(vault_id, type, normalized_name, canonical_path or "")`
- sort relationships by `(source_vault_id, type, source_entity_id,
  target_vault_id, target_entity_id)`
- sort evidence refs by their deterministic IDs

Stable sorting is required so test fixtures and rebuilds are predictable.

## 14. Tombstones

Tombstones are scoped derived state.

Rules:

- a narrow run must not tombstone graph records outside its actual scopes
- tombstone reason values should be small and stable:
  - `missing_from_scope`
  - `stale_extraction_spec`
  - `source_chunk_removed`
  - `source_document_removed`
- entity tombstones use `record_kind="entity"`
- relationship tombstones use `record_kind="relationship"`
- `GraphStore.apply_reconcile_plan` keeps the latest tombstone per
  `(record_kind, record_vault_id, record_id, actual_scope)`

Tombstoning a relationship may mark the stored relationship `deprecated`.
Tombstoning an entity may mark the stored entity `tombstoned`. This affects
derived graph visibility only; it does not delete or mutate Vault content.

## 15. Graph Revisions

Each graph apply records:

- one `graph_run_id` for the whole graph step
- one `GraphRevision` row per actual scope
- current `GraphExtractionSpec` version and digest
- metadata index revision lineage for that actual scope
- parser version
- chunker version
- graph store schema version
- entity count
- relationship count
- stale count
- tombstone count
- updated timestamp

For multi-vault runs, the graph run ID may be shared, but revision rows remain
per Vault/actual scope.

No revision row may represent a global all-vault union.

The metadata, parser, and chunker lineage values must use the same aggregate
lineage calculation as `ReadOnlyGraphReadiness`: collect the current values in
the actual scope, dedupe them, sort them, and join them into a stable string.
This keeps graph freshness comparable even when an incremental metadata run
contains unchanged chunks from older metadata revisions.

## 16. CLI And Status Surface

`vg index` text output should add graph fields after vector fields:

- `graph_mode`
- `graph_run_id`
- `graph_revision`
- `graph_entities_upserted`
- `graph_relationships_upserted`
- `graph_evidence_refs_upserted`
- `graph_tombstones`
- `graph_stale`
- `graph_extraction_spec_version`
- `graph_extraction_spec_digest`
- `graph_failed`
- `graph_last_error`

`vg index --dry-run` should render planned graph counts with the same field
names, but it must not create graph storage.

`vg status` already has Phase 3A graph readiness fields. Phase 3B makes those
fields meaningful after indexing:

- graph freshness can become `fresh`
- stale counts reflect readiness warnings and stored graph revision stale counts
- last graph revision reflects the selected actual scope
- recovery hints can recommend rerunning `vg index` for affected scopes

Exact planned graph reconcile counts belong to `vg index --dry-run` and
`vg index`, because computing them requires running `GraphIndexer.plan`.

Machine-readable status must keep the existing `graph` object and scope rows.
If `vg index` later gains JSON output, it should use the same field names as
the text output.

## 17. Error Handling

Domain errors should stay small and explicit.

Expected error classes:

- `GraphIndexingError`: base error for graph indexing failures
- `GraphExtractionError`: extractor produced invalid or unsupported occurrence
- `GraphReconcileError`: desired state cannot be reconciled with manifest state
- existing `GraphStoreError` subclasses for backend and schema failures

Error policy:

- metadata failure aborts graph indexing
- vector failure does not hide graph planning or graph apply when metadata
  succeeded
- graph failure returns a nonzero index exit code
- graph failure must not roll back a successful metadata revision
- graph failure must not roll back a successful vector revision
- graph failure must be visible in `vg index` output and `vg status`
- invalid graph records fail loudly rather than being dropped silently
- unresolved local links become warnings and concept mentions, not exceptions

Readiness policy:

- incompatible graph schema blocks graph apply
- missing graph store in apply mode may be created under the configured Vault
  Graph state path
- missing graph store in dry-run or status mode must not be created
- unsupported mixed-width graph content scopes fail before graph apply, while
  metadata/vector work may still report their own result according to the app
  service policy
- stale `GraphExtractionSpec` can be repaired by reindexing selected scopes
- incompatible schema requires migration or rebuild guidance

## 18. Multi-Vault Rules

Phase 3B must preserve multi-vault identity from the start.

Rules:

- input scopes are expanded into per-Vault actual scopes before graph planning
- `MetadataStore.list_chunks` is called per actual scope
- document resolution includes both `vault_id` and `document_id`
- graph records include Vault IDs according to Phase 3A contracts
- entity identity includes `vault_id`
- relationship identity includes source and target Vault IDs
- graph evidence refs include evidence Vault ID
- graph revisions are written per Vault/actual scope
- identical headings, tags, aliases, paths, or chunk IDs in different Vaults do
  not collide
- cross-Vault entity merging is forbidden
- Phase 3B v1 does not infer cross-Vault relationships by name

If future syntax explicitly names a different Vault, that must be designed as a
new extraction rule and a new `GraphExtractionSpec` version.

## 19. Read-Only Boundary

Allowed writes:

- configured graph store under Vault Graph state
- vector state when vector indexing is enabled
- metadata state during metadata indexing
- vector status state

Forbidden writes:

- registered Vault roots
- Vault `raw/`
- Vault `wiki/`
- Vault `docs/`
- Vault `scratch/`
- Vault Git metadata
- embedding model cache during graph-only status or graph dry-run
- projection cache creation before Phase 3C

Graph extraction may read document text and frontmatter through metadata. It
must not open Vault files directly after metadata indexing has produced the
current chunk view.

## 20. Sustainability And Scale-Up

Phase 3B keeps the local implementation simple while preserving future scale-up.

Sustainable now:

- scope-local reconcile avoids global tombstone mistakes
- deterministic IDs make rebuilds stable
- tombstones preserve stale-state explanation without hard deletes
- graph revisions make freshness inspectable
- `GraphExtractionSpec` makes extraction changes explicit
- `GraphStore` keeps SQLite replaceable
- every user-visible future result can resolve evidence through `MetadataStore`

Scale-up later:

- Neo4j can implement the same `GraphStore` contract
- more extractors can be added behind `GraphExtractionSpec`
- runtime traversal can be added in Phase 3C through `GraphProjection`
- cross-Vault references can be added only with explicit syntax and tests
- natural-language relationship extraction can be added after precision gates
  exist

Phase 3B should not introduce a generic plugin framework for extractors. A
single deterministic local extractor module is enough until a second real
extractor exists.

## 21. Testing

Required unit tests:

- document-level entity extraction from `wiki/`, `raw/`, and generic document
  paths
- decision entity extraction from decision path and frontmatter
- heading concept extraction with generic-heading filtering
- frontmatter tag concept extraction
- Markdown link and wiki-link parsing
- unresolved link handling as concept mention
- relationship extraction for `mentions`, `links_to`, and frontmatter fields
- deterministic IDs for extracted entities, relationships, and evidence refs

Required graph indexer tests:

- dry-run produces a `GraphReconcilePlan` without creating graph files
- apply writes entity, relationship, evidence, tombstone, and revision rows
- second identical run reports no stale records
- content change updates evidence hash and graph revision
- frontmatter-only change updates graph records through metadata revision
- deleted document tombstones affected entities and relationships
- mixed-width content-scope graph indexing fails with a clear domain error
- full rebuild remains inside selected actual scopes
- vector failure does not prevent graph indexing when metadata succeeded
- metadata failure prevents graph indexing

Required multi-vault tests:

- same heading in two Vaults produces different entity IDs
- same document path in two Vaults produces different entity IDs
- same relationship label in two Vaults produces different relationship IDs
- all-vault indexing records per-Vault graph revisions
- `include_cross_vault=False` does not create cross-Vault relationships

Required read-only tests:

- `vg index --dry-run` does not write Vault files
- `vg index --dry-run` does not create graph storage
- graph extraction does not open or mutate Vault files directly
- graph source document resolution is Vault-scoped
- graph apply writes only under configured Vault Graph state
- changing the graph extraction spec digest also changes the spec version
- `vg status` remains read-only before and after graph indexing

Required integration tests:

- `vg index` output includes graph counts
- `vg status --format json` reports fresh graph readiness after graph indexing
- incompatible graph schema blocks graph apply with recovery guidance
- stale `GraphExtractionSpec` is repaired by reindexing selected scopes
- unsupported graph content-scope width reports a recovery hint to rerun graph
  indexing at the whole selected Vault scope

## 22. Implementation Handoff

Recommended implementation order:

1. Add extractor occurrence dataclasses and tests.
2. Add deterministic entity extraction for document identity, headings, tags,
   and links.
3. Add deterministic relationship extraction for mentions, links, and explicit
   frontmatter relationship fields.
4. Add `GraphIndexer.plan` over fake metadata and in-memory graph store.
5. Add a Vault-scoped `GraphSourceStore` adapter over `MetadataStore` for
   apply.
6. Extend metadata preview with a Vault-scoped `GraphSourceStore` view for
   dry-run.
7. Add app-layer validation for supported graph scope width.
8. Add `GraphIndexer.apply` through the existing `GraphStore` interface.
9. Wire `IndexService.run_plan` and `IndexService.run_apply` to graph planning
   and graph apply.
10. Extend CLI index output with graph fields.
11. Add SQLite-backed graph indexing integration tests.
12. Verify full suite, lint, typing, and read-only boundary tests.

Stop after graph indexing and status freshness. Do not add graph commands,
ranking, projection traversal, or search integration in Phase 3B.

## 23. Self-Grill Results

Question: Does Phase 3B make Vault Graph a durable knowledge source?

Answer: No. The design stores only derived graph state, requires evidence refs,
and keeps durable publication outside Vault Graph.

Question: Is the extractor too weak to be useful?

Answer: It is intentionally conservative but still useful. Document identity,
decision pages, headings, tags, and explicit links are enough to power early
related-item and decision-trace prototypes without noisy semantic guesses.

Question: Can this scale beyond SQLite?

Answer: Yes. `GraphIndexer` produces the existing `GraphReconcilePlan`, and
backends only need to satisfy `GraphStore`.

Question: Can a graph index corrupt other Vaults or overlapping scopes?

Answer: The design forbids global manifests, requires per-Vault actual scopes,
keeps graph tombstones scoped, tests multi-vault collisions, and rejects
mixed-width content-scope graph indexing until an overlap-aware manifest exists.

Question: Is there a hidden user-facing behavior change?

Answer: No. `vg index` and `vg status` gain graph indexing and freshness
visibility. Default `vg search "query"` remains keyword/vector search until
Phase 3C explicit graph modes exist.

## 24. Decision Checkpoints Before Implementation

No new user decision is required before implementing this Phase 3B design. The
major policy choices are already fixed by existing project direction:

- local deterministic graph extraction first
- no LLM-required extraction
- no default graph search expansion
- no cross-Vault entity merging
- scope-local graph reconcile

Implementation should return to the user for approval before adding any of
these future changes:

- LLM-assisted extraction
- general noun-phrase extraction
- graph embeddings
- implicit graph expansion in plain search
- cross-Vault link syntax or entity merging
- Neo4j or another hosted graph backend as a default path
