# Round 0-G Authority And Projection Hygiene Design

Status: Approved for implementation

Date: 2026-08-03

Source contracts:

- `docs/SPEC.md` 1.2
- `docs/DESIGN.md`
- `docs/DECISIONS.md` — Gate Expansion On Projection Deduplication
- `docs/superpowers/reports/2026-07-30-vault-projection-duplication-direction-report-ko.md`

## 1. Goal

Complete the Vault Graph half of Round 0 by making document authority roles and
provenance families machine-readable, keeping each distinct derived chunk body
in one canonical store, removing plaintext ownership from keyword and graph
projections, collapsing default search results by provenance family, and
measuring the completion gate before code indexing begins.

## 2. Scope

In scope:

- deterministic role classification for indexed Vault documents
- deterministic provenance-family construction from Vault paths and
  frontmatter relationships
- canonical content-blob ownership in the metadata store
- contentless SQLite FTS with reference metadata in a normal table
- graph evidence references without persisted excerpts
- role-aware search modes and provenance-family result collapse
- supporting-evidence and audit links on the representative result
- read-only projection-hygiene audit metrics
- transactional full rebuild into a new projection generation
- schema/version changes, CLI/MCP serialization, documentation, and tests

Non-goals:

- Vault file changes or Vault contract changes; Round 0-V already owns them
- automatic duplicate-page merging or semantic equivalence decisions
- code repository registration or code indexing
- a writable memory layer or durable answer/context storage
- migration of individual v1 rows in place
- deletion of a previous projection generation after activation

## 3. Authority Roles

`DocumentRole` is a closed vocabulary stored on documents and chunks:

| Role | Deterministic rule | Default knowledge search |
| --- | --- | --- |
| `raw_evidence` | path under `raw/` | supporting only |
| `canonical_knowledge` | non-special page under `wiki/` | representative candidate |
| `source_manifest` | `wiki/sources/` or frontmatter `type: source` | supporting only |
| `operating_contract` | path under `docs/` | operating mode only |
| `generated_view` | `wiki/index.md`, `wiki/maps/`, or generated map/index frontmatter | audit only |
| `operation_log` | `wiki/log.md` or frontmatter `type: log` | audit only |
| `audit_record` | path under `scratch/reports/` | audit only |

Path-specific rules win over generic frontmatter rules. Classification is pure,
does not inspect mutable Vault Graph state, and returns the same role for the
same path/frontmatter pair.

Search modes map to eligible representative roles:

- `knowledge` (default): `canonical_knowledge`
- `evidence`: `source_manifest`, `raw_evidence`
- `operating`: `operating_contract`
- `audit`: `generated_view`, `operation_log`, `audit_record`
- `all`: every role

Modes change retrieval eligibility, not authority. Explicit modes may return
multiple roles from one family. Default knowledge mode returns at most one
representative per family and attaches family members as references.

## 4. Provenance Families

### 4.1 Direct links

The indexer builds an undirected provenance graph per Vault from:

- `canonical_source`
- `derived_from`
- `supersedes`
- `redirects`

Frontmatter values may be one string or a list. Vault wiki links without a file
extension are normalized to `.md`; relative Vault paths are normalized without
leaving the Vault namespace. Missing targets remain recorded as external family
seeds but never create metadata documents.

### 4.2 Family identity

Connected indexed documents share a `provenance_family_id` derived from:

```text
sha256("provenance-family", vault_id, lexicographically-smallest normalized member/seed path)
```

An unlinked document forms a one-member family. Equal content hashes do not join
families. Multi-source durable pages join all connected source manifests and raw
sources into one family. Family recomputation runs over the complete selected
Vault snapshot; a changed family ID marks affected documents for metadata
reconcile.

### 4.3 Representative priority

Knowledge-mode collapse selects one result per family with this deterministic
priority:

1. active `canonical_knowledge`
2. active `source_manifest`
3. `raw_evidence`
4. `operating_contract`
5. `generated_view`, `operation_log`, or `audit_record`

Within one role, higher fused score wins, then lower signal rank, Vault ID,
path, and chunk ID. Contested, deprecated, or human-locked records are never
silently merged with another family; they keep their provenance identity and
status metadata. A representative result carries:

- `provenance_family_id`
- its normal evidence and signals
- `supporting_evidence`: resolved family members with source/evidence roles
- `audit_records`: resolved generated/log/report family members

The two reference lists contain evidence identities, not copied excerpts.

## 5. Single-Body Metadata Projection

Metadata schema version becomes `metadata-v2`.

```text
documents
  + source_role
  + provenance_family_id

content_blobs
  blob_hash PRIMARY KEY
  text NOT NULL
  byte_count NOT NULL

chunks
  - text
  + blob_hash REFERENCES content_blobs(blob_hash)
  + source_role
  + provenance_family_id
```

`ChunkSnapshot.text` remains the application DTO for parsing, embedding, and
rendering. SQLite reconstructs it by joining `chunks.blob_hash` to
`content_blobs`. Applying a revision inserts blobs with `INSERT OR IGNORE`,
replaces chunk references, then garbage-collects unreferenced blobs inside the
same transaction. Logical document/chunk identities remain Vault-scoped even
when two chunks share a physical blob.

## 6. Reference-Only Keyword Projection

Keyword schema version becomes `sqlite-keyword-v2`.

- `keyword_chunks` is an FTS5 contentless table. It owns token postings only.
- `keyword_rows` maps the FTS row ID to Vault/document/chunk identity,
  `source_role`, `provenance_family_id`, content scope, and revision.
- title, path, section, selected frontmatter, and chunk text are supplied to FTS
  during indexing but cannot be selected back as stored plaintext.
- matched fields are determined from column-scoped FTS queries over postings,
  not from copied field values.
- role filters run before the result limit.
- hits return identities, rank, score, matched fields, role, family, backend,
  and revision; rendering still resolves through `MetadataStore`.

## 7. Reference-Only Vector And Graph Projections

Vector records add `source_role` and `provenance_family_id` filter metadata but
continue to store only embeddings and identifiers. Vector queries accept role
filters and apply them before limits. Contract tests inspect Chroma metadata and
reject plaintext-bearing keys such as `text`, `document`, `excerpt`, `summary`,
or `body`.

Graph schema version becomes `sqlite-graph-v2`. `GraphEvidenceRef` and
`graph_evidence_refs` remove `excerpt`. They retain evidence chunk identity,
content hash, section, anchor, path, and revision linkage. CLI, MCP, related,
decision-trace, and resource rendering resolve user-visible excerpts from the
metadata chunk at request time.

## 8. Retrieval Flow

```text
SearchRequest(mode=knowledge)
  -> mode role policy
  -> per-Vault actual scopes
  -> keyword/vector/optional graph candidates filtered by role before limits
  -> fuse by (vault_id, chunk_id)
  -> resolve metadata evidence and chunk
  -> group by (vault_id, provenance_family_id)
  -> select representative
  -> resolve bounded supporting/audit evidence references
  -> apply final limit
  -> SearchResponse
```

Graph candidates without role metadata are resolved through metadata before
eligibility and collapse. Missing family or role metadata is a schema
incompatibility, not an implicit canonical-knowledge default in persisted v2
state.

CLI adds `vg search --mode knowledge|evidence|operating|audit|all`. MCP
`search_vault` adds the same optional mode with `knowledge` as the default.
Context, answer, and memory services inherit knowledge-mode search unless they
explicitly request another mode.

## 9. Transactional Rebuild And Activation

Projection layout version is `projection-layout-v1`.

Legacy/current paths remain readable until a rebuild is activated. A full
rebuild creates:

```text
STATE/projections/generations/<generation_id>/
  metadata/metadata.sqlite3
  vector/chroma/
  vector/status.json
  graph/graph.sqlite3
  graph/status.json
```

The rebuild flow is:

1. inspect the current active or legacy projection read-only
2. create a unique staging generation under the state root
3. build metadata, keyword, vector, and graph state only in that generation
4. run health/schema checks and dangling-reference audit
5. when every enabled projection succeeds, atomically replace
   `STATE/projections/active.json`
6. on failure, leave the old active projection unchanged and remove only the
   failed staging generation

`active.json` contains layout version, generation ID, activation timestamp, and
relative generation path. Path traversal, symlinks, absolute relative-path
fields, and generations outside the state root are rejected. Previous
generations are retained for rollback/audit and are not deleted automatically.

Incremental indexing writes only the active compatible generation. A v1 schema
opened for write returns `projection_migration_required` with the recovery hint
`vg index --full`. Dry-run reports that a generation rebuild is required but
does not create directories.

## 10. Projection Hygiene Audit

`ProjectionHygieneService.audit(scope, queries=())` is read-only and returns:

- document and chunk counts by role
- canonical blob count and UTF-8 byte count
- logical chunk UTF-8 byte count
- FTS and graph persisted plaintext byte counts
- `plaintext_amplification`
- dangling keyword, vector, and graph reference counts
- generated/audit document counts in the default catalog scope
- query result count and repeated-family count for supplied queries
- `result_family_duplication`
- schema versions and active generation identity

The byte metric is:

```text
plaintext_amplification =
  (canonical_blob_bytes + persisted_search_projection_plaintext_bytes)
  / canonical_blob_bytes
```

Logical duplicate chunk references are reported separately and do not count as
additional plaintext when they share one blob. With no supplied queries,
result-family duplication is `null`, not an invented zero.

CLI adds:

```text
vg projection-audit --state PATH --query QUERY --format text|json
```

The command never initializes a store or mutates state.

## 11. Errors And Edge Cases

- malformed relation frontmatter: classify the document, ignore the malformed
  relation value, and emit an index warning
- relation target outside allowed Vault-relative paths: reject that link seed
- missing relation target: preserve a deterministic external seed; do not
  create an evidence record
- empty documents: keep the document role/family; create no blob or chunk
- equal body, different provenance: share the blob and keep distinct chunks
- missing blob for a chunk: metadata health is incompatible and retrieval fails
- FTS/vector/graph hit missing a chunk: drop it, count a dangling reference, and
  emit a warning
- explicit evidence/audit/all mode: do not collapse away requested family
  members
- multi-Vault: family IDs and grouping always include Vault ID
- rebuild interruption before activation: the old manifest remains valid
- invalid active manifest: fail closed with a recovery hint; never guess a path

## 12. Tests

Focused tests cover:

- role classification precedence and all seven roles
- provenance union, missing seeds, multi-source families, and multi-Vault
  separation
- one blob for equal chunk text with distinct chunk/evidence identities
- blob garbage collection after replacement/tombstone
- contentless FTS schema, role filtering before limits, and evidence resolution
- vector metadata contains no plaintext and filters roles before limits
- graph v2 schema has no excerpt column and graph output resolves metadata
- knowledge-mode family collapse, representative priority, supporting/audit
  references, explicit-mode expansion, and deterministic ranking
- audit metrics, zero dangling refs, and read-only behavior
- full rebuild activation, failure rollback, manifest path safety, and v1
  migration-required behavior
- CLI/MCP mode serialization and no Vault/state mutation during search/audit

## 13. Verification And Completion Gate

Run:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv build
```

Then index a disposable state from the local Vault, run representative Korean
and English audit queries, delete the active derived generation, rebuild from
the same Vault revision, and compare audit/search output after removing runtime
timestamps and generated revision IDs.

Round 0-G is complete only when:

- `plaintext_amplification == 1.0`
- default knowledge search has `result_family_duplication == 0.0`
- dangling keyword/vector/graph references are all zero
- evidence and citation resolution remain successful
- rebuild output is functionally equivalent
- Vault tracked and untracked file fingerprints are unchanged
- no implementation for Round 1 code indexing is present

## 14. Open Decisions

None. The product and architecture choices were accepted in the 2026-07-30
direction and decision records.
