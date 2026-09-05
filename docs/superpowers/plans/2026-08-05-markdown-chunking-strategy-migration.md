# Format-Neutral Document Chunking Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the final format-neutral hierarchical evidence-index boundary first, then deliver it through independently verifiable slices that migrate Markdown from unbounded heading sections to deterministic structural windows without redesigning the system for PlainText, PDF, or DOCX.

**Architecture:** `VaultLoader` discovers and hashes source bytes, `DocumentReaderRegistry` selects a read-only format adapter, and each adapter emits a common `ExtractedDocument` made of structural units with source locators and extraction lineage. A shared `DocumentChunker` packs those units into non-overlapping leaf retrieval chunks. `MetadataStore` remains the authority for raw chunk text, chunk identity, locators, section paths, and document order; keyword/vector projections reference that authority, while retrieval derives parent/neighbor context from those fields under `QueryScope` and a context budget. The implementation slices prove each boundary independently before composing them.

**Tech Stack:** Python 3.12, deterministic state-machine Markdown parsing, SQLite metadata and FTS5 projections, Chroma, FastEmbed, pytest, ruff, mypy.

---

## Scope

Design the final indexing boundary now and implement it through independent
slices. The migration in `docs/TODO.md` becomes the first production slice of
that final structure, not a disposable Markdown-only architecture:

```text
source bytes
  -> reader-neutral structural units
  -> bounded leaf retrieval chunks
  -> keyword/vector projections
  -> query-time parent/neighbor context expansion
```

The final target has four stable contracts:

1. **Extraction contract.** `DocumentReaderRegistry` selects a read-only reader
   and returns `ExtractedDocument` with structural units, source locators,
   reader lineage, and warnings.
2. **Chunk contract.** `DocumentChunker` creates bounded, non-overlapping leaf
   `RetrievalChunk` drafts from any extracted document. It does not know
   Markdown, PDF, DOCX, or PlainText syntax.
3. **Evidence contract.** `MetadataStore` owns raw extracted text, stable chunk
   identity, section paths, source locators, and deterministic document order.
4. **Retrieval contract.** Vector and keyword search return matched leaf IDs;
   retrieval may expand those IDs into bounded context without changing vector
   records or the Vault source.

The implementation is split into independently verifiable slices:

- **Slice A — final contracts:** pure models and fake-reader contract tests;
  no user-visible indexing behavior changes.
- **Slice B — Markdown extraction:** Markdown becomes the first adapter of the
  final extraction contract; parser tests run without SQLite or embeddings.
- **Slice C — pure chunk planning:** generic bounded chunk planning and stable
  boundary tests run against Markdown and synthetic PDF/DOCX-like fixtures.
- **Slice D — evidence/projection migration:** normalizer, metadata schema,
  keyword/vector projections, and stale-state reconciliation persist the final
  chunk/evidence shape; SQLite and fake projection tests remain independent of
  retrieval policy.
- **Slice E — retrieval context:** parent/neighbor expansion is verified over
  ordered metadata chunks without touching vector records.
- **Slice F — real-reader expansion:** PlainText, DOCX, and PDF are separate
  adapter slices, each with its own dependency and locator verification.

The migration addresses the current implementation's concrete weaknesses:

- `parse_sections()` recognizes headings with a regular expression and does not
  understand fenced-code state.
- One heading section can become an arbitrarily large chunk.
- The vector input is only `chunk.text`, so structural context is absent from
  semantic retrieval.
- Current chunk IDs include the enumerated section position, so inserting an
  unrelated section can change IDs for later sections.
- Keyword search stores only the leaf section heading, not its full structural
  context.
- The current `LoadedVaultDocument` is Markdown-shaped, so a PDF or DOCX reader
  would otherwise need to bypass or duplicate the ingestion contract.

The new version will:

- hash source bytes before format-specific decoding;
- select a reader through `DocumentReaderRegistry` without changing the
  read-only Vault boundary;
- emit common structural blocks with `section_path`, deterministic block keys,
  extraction warnings, and source locators;
- pack adjacent blocks into non-overlapping windows under a versioned budget;
- preserve fenced code blocks and tables unless deterministic oversized-block
  splitting is required;
- keep raw chunk text separate from context-augmented embedding text;
- derive chunk IDs from stable structural boundaries instead of section ordinal;
- persist generic section paths and source locators in the metadata projection;
- rebuild keyword and vector projections through the existing `vg index` flow;
- cause the existing version reconciliation to re-embed selected scopes and
  tombstone old-version vectors;
- allow future PlainText, PDF, and DOCX adapters to implement extraction and
  locator rules without changing the shared chunk planner, stores, or retrieval
  contract.

## Non-goals

- Do not implement PlainText, PDF, or DOCX extraction in this slice; define and
  contract-test the adapter boundary so those readers can be added later.
- Do not implement answer-generation changes or a second source of durable
  knowledge. The retrieval slice may add the final matched-leaf plus
  parent/neighbor context contract, but it must remain an evidence-linked
  projection over `MetadataStore`.
- Do not add vector overlap windows. Retrieval-time neighbor expansion is the
  later mechanism for context expansion.
- Do not add a Markdown dependency or a model-specific tokenizer in the first
  implementation slice.
- Do not change the canonical evidence identity
  `(vault_id, document_id, chunk_id)`.
- Do not persist synthetic context text as Vault content or as the raw
  `ChunkSnapshot.text` authority.
- Do not change source files under a registered Vault.
- Do not change the separate AST-based code projection.
- Do not add a user-facing chunk-size CLI option before a retrieval benchmark
  demonstrates that one is needed.

## Repo context

Read and reconcile against:

- `docs/SPEC.md`: read-only/rebuildable boundaries, `ChunkSnapshot`, metadata and
  vector contracts, incremental indexing, and evidence-first retrieval.
- `docs/DESIGN.md`: ingestion, chunking, metadata ownership, vector reconcile,
  retrieval, and testing boundaries.
- `docs/FEATURES.md`: `vg index`, dry-run, status, and user-visible guarantees.
- `docs/CONVENTIONS.md`: module boundaries, typing, naming, and test style.
- `docs/TODO.md`: the non-Markdown adapter boundary, v2 requirements, and the
  separate retrieval-context direction.

Current implementation points:

- `src/vault_graph/ingestion/vault_loader.py`: Markdown-only discovery,
  decoded-text hashing, and the current `LoadedVaultDocument` shape.
- `src/vault_graph/ingestion/markdown_parser.py`: heading regex and section
  extraction.
- `src/vault_graph/ingestion/document_normalizer.py`: `heading-section-v1`,
  chunk identity, raw chunk hash, and `ChunkSnapshot` construction.
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: canonical chunk body,
  chunk metadata, and keyword projection update.
- `src/vault_graph/indexing/vector_indexer.py`: embedding input and stale-vector
  comparison.
- `src/vault_graph/storage/local/sqlite_keyword_index.py`: FTS5 fields and
  chunk-level keyword projection.
- `src/vault_graph/retrieval/retrieval_service.py`: candidate fusion and
  evidence resolution; context expansion must be added only after those
  existing steps and must not replace their matched evidence.
- `tests/test_document_normalizer.py`, `tests/test_metadata_indexer.py`,
  `tests/test_metadata_chunk_listing.py`, and `tests/test_vector_indexer.py`:
  existing chunk identity and stale-vector coverage.

The TODO boundary is intentionally the target shape:

```text
VaultLoader
  -> DocumentReaderRegistry
      -> MarkdownDocumentReader
      -> PlainTextDocumentReader  (future)
      -> PdfDocumentReader        (future)
      -> DocxDocumentReader       (future)
  -> DocumentNormalizer
  -> MetadataStore
  -> VectorIndexer
```

The plan makes the arrow between the registry and normalizer explicit by
introducing `ExtractedDocument` and `ContentBlock` contracts. No future reader
is enabled by default as part of this migration.

## Design recommendation

### 1. Put a format-neutral extraction contract before the chunker

The chunker must receive semantic blocks, not Markdown syntax. Add a common
ingestion model that every future reader can produce:

```python
BlockKind = Literal[
    "heading",
    "paragraph",
    "list",
    "blockquote",
    "code",
    "table",
    "caption",
    "page_break",
    "other",
]


@dataclass(frozen=True)
class SourceLocator:
    scheme: str
    coordinates: tuple[tuple[str, str], ...]
    start_offset: int | None = None
    end_offset: int | None = None
    offset_unit: Literal["byte", "char", "line", "none"] = "none"


@dataclass(frozen=True)
class ContentUnit:
    text: str
    source_locator: SourceLocator
    stable_key: str


@dataclass(frozen=True)
class ContentBlock:
    kind: BlockKind
    section_path: tuple[str, ...]
    units: tuple[ContentUnit, ...]
    stable_key: str
    searchable_label: str | None = None
```

`ContentUnit` is the smallest safe packing unit emitted by a reader. It is not
an arbitrary token window. For example, a Markdown adapter emits paragraph
sentences or lines only when a paragraph is oversized, a PDF adapter emits
page-local text spans, and a DOCX adapter emits paragraph/list/table-row units.
The shared planner concatenates units but never parses PDF layout, DOCX XML, or
Markdown syntax.

The reader boundary is:

```python
@dataclass(frozen=True)
class SourceDocument:
    vault_id: str
    root_path: Path
    path: str
    suffix: str
    raw_bytes: bytes
    raw_sha256: str


@dataclass(frozen=True)
class ExtractedDocument:
    source: SourceDocument
    format: str
    reader_name: str
    reader_version: str
    parser_version: str
    extraction_options_digest: str
    frontmatter: FrontmatterProjection
    blocks: tuple[ContentBlock, ...]
    warnings: tuple[ExtractionWarning, ...]
```

`DocumentReaderRegistry` selects a `DocumentReader` by suffix and optional
capability. The registry initially registers only `MarkdownDocumentReader`.
Unsupported files remain outside the default Markdown scan until a future
adapter is explicitly enabled. Optional dependencies and extraction failures
become warnings/status records, not silent parser fallbacks.

The locator is deliberately separate from chunk identity. Examples are:

| Reader | Structural context | Locator coordinates | Safe units |
| --- | --- | --- | --- |
| Markdown | heading levels -> `section_path` | line/character range and block ordinal | paragraph sentences, code lines, table rows |
| PlainText | usually empty `section_path` | line/character range | paragraphs or lines |
| PDF | only headings confidently inferred by the adapter | page number plus extracted-text offsets | page paragraph/line spans, table rows |
| DOCX | heading styles -> `section_path` | paragraph/list/table/cell coordinates | paragraphs, list items, table rows |

Page numbers, paragraph indices, and line offsets are evidence coordinates;
they must not be the only input to a chunk ID because layout or preceding
content can move them.

### 2. Make the shared planner format-neutral

`DocumentChunker` consumes `ExtractedDocument.blocks` and produces generic
`ChunkDraft` records. It does not import `markdown_parser`, PDF libraries, or
DOCX libraries. Its policy has one versioned budget; the initial candidate is
`256` estimated tokens, subject to the benchmark decision under `Open
Decisions`.

Packing rules:

- Start a new window when adding the next `ContentUnit` would exceed the
  budget.
- Do not combine content across a same-or-higher-level structural boundary
  when the reader marks that boundary with a new `section_path`.
- Keep adjacent units under the same section path together whenever the budget
  permits.
- Preserve each unit's locators in the resulting draft; a chunk may have more
  than one locator when it spans paragraphs or pages.
- If a reader emits an oversized unit, use the reader's deterministic safe
  units first, then a generic whitespace fallback as the last resort and emit
  a warning. The planner never silently violates the budget.
- Do not use token overlap in v2. Retrieval-time parent or neighbor expansion
  is the later context mechanism.

The Markdown reader-specific rules remain at the adapter boundary:

- recognize headings only outside backtick or tilde fences;
- keep fenced code as code units and tables as row units;
- track heading levels into `section_path`;
- retain heading-only blocks and represent preamble text with an empty path;
- preserve source text apart from existing surrounding-whitespace
  normalization.

This keeps the hard part reusable: a future PlainText, PDF, or DOCX reader only
has to emit stable units and locators, while the budget, boundary identity,
metadata persistence, and vector reconciliation stay shared.

### 3. Keep raw evidence, context text, and locators separate

`ChunkSnapshot.text` remains the extracted raw body stored in `MetadataStore`.
It is not the original PDF/DOCX bytes, and it is never augmented with synthetic
context. A chunk also stores `section_path` and `source_locators` so evidence
can show both semantic context and format-specific location.

The embedding input is generated by a format-neutral pure function:

```python
def contextual_embedding_text(*, section_path: tuple[str, ...], text: str) -> str:
    breadcrumb = " > ".join(section_path)
    if not breadcrumb:
        return text
    return f"Section path: {breadcrumb}\n\n{text}"
```

The context prefix is part of `document-block-window-v2`. Changing it requires
a new chunker/projection version so existing vectors are reconciled. Source
locators are not included in the embedding text; page numbers and XML/table
coordinates are evidence metadata, not semantic content.

### 4. Use structural boundary identity for chunk IDs

The normalizer should construct IDs from:

```python
stable_id(
    "chunk",
    CHUNKER_VERSION,
    vault_id,
    path,
    draft.boundary_key,
)
```

`boundary_key` contains the first and last `ContentUnit.stable_key`, the
section path, and an oversized-fragment ordinal. Unit stable keys are based on
kind, normalized text, semantic path, and an occurrence count among identical
units in the local structural scope. They must not rely on a global section
ordinal or a source page/line number. The source locator is retained for
evidence but is not the identity anchor.

This gives stable IDs for unchanged content and unrelated edits across all
reader formats. Inserting an identical duplicate immediately before another
identical duplicate remains inherently ambiguous; the occurrence count is the
deterministic fallback and the tests must document that limitation.

Reader/parser lineage changes are freshness inputs even when extracted text is
unchanged. They must cause the document to be re-normalized and the selected
metadata/vector scope to reconcile; they do not require a reader-specific
chunker implementation.

### 5. Persist generic structure and source evidence

Use generic names in the canonical model. `heading_path` would make the
Markdown implementation leak into PlainText/PDF/DOCX, so the shared field is
`section_path`. Keep the existing leaf `section` and `anchor` fields as
compatibility projections for current evidence and graph consumers.

The metadata schema becomes `metadata-v3` and adds:

- document lineage: `format`, `reader_name`, `reader_version`, and
  `extraction_options_digest`;
- chunk structure: `section_path_json` and `document_order`;
- chunk evidence: `source_locators_json`.

`ChunkSnapshot` and `EvidenceReference` expose `section_path` and
`source_locators` with empty defaults for existing test/fake constructors. The
SQLite store serializes these as deterministic JSON and validates the decoded
shape before returning evidence. The initialized indexing open may add the
new columns; read-only status/search must fail closed with an `vg index`
recovery hint rather than mutating state.

The first v2 index rewrites selected documents and fills these fields. Future
PDF page locators and DOCX table/paragraph locators then flow through the same
MetadataStore resolution path without changing `VectorStore` or retrieval
identity.

Retrieval context is a separate policy over the stored fields. Add a
`ContextExpander` that accepts a matched leaf chunk, `QueryScope`, and context
budget, then returns:

```python
@dataclass(frozen=True)
class ContextExpansion:
    matched_chunk_id: str
    context_chunk_ids: tuple[str, ...]
    parent_section_path: tuple[str, ...]
    reason: str
    policy_version: str
    warnings: tuple[RetrievalWarning, ...]
```

The expander reads ordered chunks through `MetadataStore`, never adds context
vectors, and never crosses the requested Vault/content scope. A retrieval
policy change therefore does not stale vectors when leaf chunk text and
`CHUNKER_VERSION` are unchanged.

## Independent slice contracts

Each slice must have a usable exit condition and a narrow failure boundary. A
later slice may consume an earlier contract, but it must not require a live
embedding model, optional PDF/DOCX dependency, or Vault mutation merely to test
its own behavior.

| Slice | Independent input | Independent verification | Exit condition |
| --- | --- | --- | --- |
| A. Final contracts | In-memory `SourceDocument` and fake `ContentBlock` values | Pure Python contract tests | Types, locator validation, deterministic serialization, and registry errors are stable |
| B. Markdown reader | UTF-8 Markdown fixture | Reader/parser tests only | Fences, tables, section paths, warnings, and locators are deterministic |
| C. Chunk planner | `ExtractedDocument` fixture, including synthetic PDF/DOCX locators | Pure chunker tests only | Bounded non-overlap, stable boundary keys, raw text preservation, and locator aggregation pass |
| D. Evidence/projection migration | Normalized documents and chunks plus recording projection fakes | SQLite, keyword, vector, and metadata-index tests | Schema upgrade, freshness lineage, round-trip evidence, contextual embedding, stale-vector reconcile, and read-only incompatibility behavior pass |
| E. Retrieval context | Ordered metadata chunks and a metadata fake | Context-policy and search contract tests | Matched-leaf/context expansion, budget, policy version, and scope boundaries pass |
| F. Reader adapters | Adapter-specific source fixtures and optional dependency | Per-reader contract suite | Each enabled reader produces valid common units and traceable locators without changing shared code |

Slice C is the key proof that the final design is not Markdown-specific. It
must pass with a synthetic document whose units use PDF page coordinates and
DOCX paragraph/table coordinates before any optional reader package is added.
Slice E proves that changing retrieval context policy does not invalidate
vectors when leaf chunk text and chunker lineage are unchanged.

## File structure

Create:

- `src/vault_graph/ingestion/document_models.py`: `SourceDocument`,
  `SourceLocator`, `ContentUnit`, `ContentBlock`, `ExtractedDocument`, and
  extraction warning contracts.
- `src/vault_graph/ingestion/document_readers.py`: `DocumentReader` protocol,
  `DocumentReaderRegistry`, and the initial Markdown reader adapter boundary.
- `src/vault_graph/ingestion/document_chunking.py`: format-neutral unit-to-window
  packing, token estimate, stable boundary keys, and contextual embedding-text
  derivation.
- `src/vault_graph/retrieval/context_expansion.py`: versioned parent/neighbor
  expansion over ordered metadata chunks, scope filtering, and context warnings.
- `tests/test_document_readers.py`: registry, raw-byte hashing, unsupported
  formats, warnings, and locator contract tests using a fake reader.
- `tests/test_document_chunking.py`: generic block packing, Markdown adapter
  fixtures, stable boundaries, locators, and oversized-unit behavior.
- `tests/test_context_expansion.py`: matched-leaf, parent/neighbor, budget, and
  QueryScope contract tests using an in-memory metadata fake.
- `tests/test_read_only_service_factory.py`: factory-created retrieval services
  use the same context policy as direct service construction.

Modify:

- `src/vault_graph/ingestion/vault_loader.py`: discover configured source files,
  hash raw bytes, and pass a `SourceDocument` to the reader registry while
  preserving the default Markdown-only policy.
- `src/vault_graph/ingestion/markdown_parser.py`: replace regex-only section
  extraction with fence-aware structural block extraction and source locators.
- `src/vault_graph/ingestion/document_normalizer.py`: consume an
  `ExtractedDocument`, use shared v2 drafts, add generic section paths/locators,
  and set `CHUNKER_VERSION` to `document-block-window-v2`.
- `src/vault_graph/storage/interfaces/metadata_store.py`: expose generic
  section paths, source locators, document order, and ordered document-chunk
  listing on document/chunk/evidence contracts.
- `src/vault_graph/storage/local/sqlite_metadata_store.py`: persist and restore
  document reader lineage, `section_path_json`, and `source_locators_json`,
  validate the metadata-v3 columns, and add the initialized schema upgrade.
- `src/vault_graph/indexing/metadata_indexer.py`: compare reader identity,
  reader version, and extraction options when deciding whether a document is
  stale.
- `src/vault_graph/indexing/vector_indexer.py`: embed the pure
  context-aware text while retaining raw `source_chunk_hash` and existing
  reconcile rules.
- `src/vault_graph/storage/local/sqlite_keyword_index.py`: index the full
  section path in the existing `section` FTS field without changing the
  keyword-hit contract.
- `src/vault_graph/app/local_index_service_factory.py`: publish the actual
  `CHUNKER_VERSION` in the metadata component manifest instead of a hard-coded
  normalizer label.
- `src/vault_graph/retrieval/retrieval_result.py`: add matched-leaf,
  context-chunk, and context-policy fields with backward-compatible defaults.
- `src/vault_graph/retrieval/retrieval_service.py`: invoke the context expander
  after candidate/evidence resolution while keeping matched evidence as the
  authority and surfacing context warnings.
- `src/vault_graph/app/read_only_service_factory.py`: construct and inject the
  context expander for CLI, MCP, and context-pack retrieval services.
- `src/vault_graph/cli/main.py`: preserve the same context-expander wiring for
  direct CLI search construction.
- `tests/test_vault_loader.py`: byte hashing, default suffix policy, and
  read-only source discovery.
- `tests/test_document_normalizer.py`: generic reader lineage, section paths,
  locators, v2 version, and stable identity expectations.
- `tests/test_metadata_indexer.py`: reader-version and extraction-option
  changes mark affected documents stale.
- `tests/test_metadata_chunk_listing.py`: section-path and locator round-trip
  assertions.
- `tests/test_metadata_evidence_resolution.py`: format-specific locator
  resolution without changing existing path/section/anchor fields.
- `tests/test_sqlite_metadata_store.py`: metadata-v3 schema and persistence
  coverage.
- `tests/test_vector_indexer.py`: assert the exact contextual embedding input
  and v2 reconcile behavior.
- `tests/test_retrieval_service_search.py`: matched leaf remains the result
  evidence while context IDs and policy version are reported separately.
- `tests/test_read_only_service_factory.py`: factory-created retrieval services
  use the same context policy as direct service construction.
- `tests/test_index_service_vector_reconcile.py`: verify the real service path
  re-embeds after the chunker version changes.
- `tests/test_cli_vector_indexing.py`: verify dry-run/apply output still shows
  selected-scope upserts and tombstones.
- `tests/test_graph_indexer.py`: verify graph evidence continues to use the
  leaf section and current v2 chunker version.

The retrieval service must not put expanded context into `VectorStore` or
replace matched evidence. Its change is limited to invoking the versioned
`ContextExpander` after the existing candidate fusion and evidence resolution.

## Implementation steps

### Task 1: Freeze the final canonical contracts without changing behavior

**Files:**

- Create: `src/vault_graph/ingestion/document_models.py`
- Create: `src/vault_graph/ingestion/document_readers.py`
- Create: `tests/test_document_readers.py`

- [x] **Step 1: Write pure contract tests.**

Add tests that construct a `SourceLocator`, a PDF-like `ContentUnit`, and a
DOCX-like table-row `ContentUnit`. Assert the following concrete values:

```python
locator = SourceLocator(
    scheme="pdf",
    coordinates=(("page", "4"), ("block", "2")),
    start_offset=120,
    end_offset=188,
    offset_unit="char",
)
assert locator.coordinates == (("page", "4"), ("block", "2"))
assert locator.start_offset == 120
assert locator.end_offset == 188
```

Also test that an invalid negative offset, reversed offset range, or unsorted
coordinate tuple raises the project contract error. Test that a fake reader
can return an `ExtractedDocument` containing both locators without importing
Markdown, PDF, or DOCX libraries.

- [x] **Step 2: Run the contract tests and verify failure.**

Run:

```bash
uv run --python 3.12 pytest tests/test_document_readers.py -q
```

Expected: FAIL because the immutable source, locator, content-unit,
extracted-document, warning, reader, and registry contracts do not yet exist.

- [x] **Step 3: Implement the immutable final contracts.**

Add `SourceDocument`, `SourceLocator`, `ContentUnit`, `ContentBlock`,
`ExtractedDocument`, and `ExtractionWarning`. Validate that locator coordinates
are sorted immutable key/value pairs, offsets are non-negative and ordered, and
JSON serialization is deterministic. Put the validation in `__post_init__` so
all reader implementations receive the same contract checks.

Add a `DocumentReader` protocol with `name`, `version`, `suffixes`, and
`read(source: SourceDocument) -> ExtractedDocument`. Add a registry that
rejects duplicate suffix registrations, returns a typed unsupported-format
diagnostic, and does not load optional dependencies during construction.

- [x] **Step 4: Run the pure contract suite.**

Run:

```bash
uv run --python 3.12 pytest tests/test_document_readers.py -q
uv run --python 3.12 mypy src/vault_graph/ingestion/document_models.py src/vault_graph/ingestion/document_readers.py
```

Expected: contract tests and type checking pass; no existing Vault or metadata
behavior has changed.

### Task 2: Make Markdown the first reader of the common block model

**Files:**

- Modify: `src/vault_graph/ingestion/vault_loader.py`
- Modify: `src/vault_graph/ingestion/markdown_parser.py`
- Modify: `src/vault_graph/ingestion/document_readers.py`
- Modify: `tests/test_vault_loader.py`
- Modify: `tests/test_document_readers.py`
- Modify: `tests/test_document_chunking.py`

- [x] **Step 1: Add failing loader and Markdown adapter tests.**

Add tests for these cases:

```python
def test_loader_hashes_original_markdown_bytes(tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    source.write_bytes("# 제목\n\n본문".encode("utf-8"))
    assert load_one_document(source).raw_sha256 == sha256(source.read_bytes()).hexdigest()


def test_heading_marker_inside_fenced_code_is_not_a_heading() -> None:
    blocks = parse_markdown_blocks("```python\n# not a heading\n```\n")
    assert [block.kind for block in blocks] == ["code"]


def test_nested_headings_emit_a_section_path() -> None:
    blocks = parse_markdown_blocks("# A\n## B\n내용\n")
    assert blocks[-1].section_path == ("A", "B")


def test_table_rows_emit_safe_units_and_locators() -> None:
    blocks = parse_markdown_blocks("| A | B |\n| --- | --- |\n| 1 | 2 |\n")
    assert blocks[0].kind == "table"
    assert len(blocks[0].units) == 3


def test_heading_only_section_is_retained() -> None:
    blocks = parse_markdown_blocks("# A\n")
    assert blocks[0].section_path == ("A",)
    assert blocks[0].units[0].text == ""


def test_preamble_has_an_empty_section_path() -> None:
    blocks = parse_markdown_blocks("서문\n")
    assert blocks[0].section_path == ()


def test_parse_sections_compatibility_view_preserves_existing_callers() -> None:
    sections = parse_sections("# A\n\n본문\n")
    assert sections[0].heading == "A"
    assert sections[0].text == "본문"
```

- [x] **Step 2: Run the focused tests and verify failure.**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_vault_loader.py \
  tests/test_document_readers.py \
  tests/test_document_chunking.py -q
```

Expected: FAIL because the loader does not yet hash raw bytes into a source
document and the Markdown reader does not yet emit generic blocks, safe units,
or source locators.

- [x] **Step 3: Implement the loader and fence-aware Markdown adapter.**

Change `VaultLoader` to read source bytes, calculate `raw_sha256` from the
bytes, and pass a `SourceDocument` to `DocumentReaderRegistry`. Preserve the
current Markdown-only `*.md` discovery and QueryScope behavior. Do not enable
`.txt`, `.pdf`, or `.docx` scanning.

Register `MarkdownDocumentReader`. It decodes UTF-8, retains the existing
frontmatter projection, and uses a deterministic state machine that emits
`ContentBlock` values. Recognize headings only outside backtick/tilde fences;
track heading levels into `section_path`; group paragraphs, lists, quotes,
code, and tables; and emit line/character locators. Preserve the existing
`parse_sections()` compatibility view for callers that still need the leaf
heading projection, but keep the normalizer on the new reader contract.

Tables are emitted with deterministic row-safe units and code with complete
line-safe units. An unterminated fence produces a bounded warning and retains
the remaining text as code.

- [x] **Step 4: Run Markdown, loader, and read-only tests.**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_vault_loader.py \
  tests/test_document_readers.py \
  tests/test_document_chunking.py \
  tests/test_read_only_boundary.py \
  tests/test_document_normalizer.py -q
```

Expected: raw-byte hashes, structural blocks, locators, and read-only behavior
pass; v1-specific normalizer expectations remain until Task 4 switches the
normalizer to v2.

### Task 3: Implement the shared window planner and v2 identity

**Files:**

- Create: `src/vault_graph/ingestion/document_chunking.py`
- Modify: `src/vault_graph/ingestion/document_normalizer.py`
- Modify: `tests/test_document_chunking.py`
- Modify: `tests/test_document_normalizer.py`

- [x] **Step 1: Add the chunk-draft contract and red tests.**

Define:

```python
DEFAULT_DOCUMENT_CHUNK_MAX_TOKENS = 256
CHUNKER_VERSION = "document-block-window-v2"


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    token_count: int
    section: str | None
    anchor: str | None
    section_path: tuple[str, ...]
    source_locators: tuple[SourceLocator, ...]
    document_order: int
    boundary_key: str
```

Expose:

```python
def chunk_document(
    document: ExtractedDocument,
    *,
    max_tokens: int = DEFAULT_DOCUMENT_CHUNK_MAX_TOKENS,
) -> tuple[ChunkDraft, ...]:
    raise NotImplementedError


def contextual_embedding_text(*, section_path: tuple[str, ...], text: str) -> str:
    raise NotImplementedError
```

The red tests must use both a Markdown fixture and a fake PDF/DOCX-like
`ExtractedDocument`. Define a `make_extracted_document(...)` test helper with
three units, two section paths, and page/paragraph locators. Prove that the
same planner:

- packs adjacent units without overlap;
- preserves all source locators in a multi-unit chunk;
- keeps section paths as context while leaving raw text unchanged;
- splits or rejects oversized units deterministically;
- produces identical boundary keys on repeated normalization;
- leaves unrelated chunk IDs unchanged when a sibling block is inserted;
- does not use page, line, paragraph, or table ordinal as the only identity.

- [x] **Step 2: Run the red chunking tests.**

Run:

```bash
uv run --python 3.12 pytest tests/test_document_chunking.py -q
```

Expected: FAIL on the missing planner, context projection, and stable-boundary
behavior.

- [x] **Step 3: Implement one forward-pass planner.**

Pack `ContentUnit` values under the deterministic estimate
`len(text.split())`, flushing before a unit would exceed the selected budget.
Use the section path to prevent unsafe cross-section packing and preserve every
unit locator. If the reader emits an oversized unit, use a deterministic
whitespace fallback while retaining the original locator; extraction warnings
remain reader-owned. Do not add overlap windows.

- [x] **Step 4: Update the normalizer to consume extracted documents.**

Change `DocumentNormalizer.normalize(...)` to accept the
`ExtractedDocument` returned by `VaultLoader` and replace
`enumerate(parse_sections(...))` with `chunk_document(extracted)`. Construct
each chunk ID from:

```python
stable_id(
    "chunk",
    CHUNKER_VERSION,
    extracted.source.vault_id,
    extracted.source.path,
    draft.boundary_key,
)
```

Keep `content_hash=stable_id("chunk-content", draft.text)` as the raw extracted
body hash. Keep the leaf `section` and `anchor` compatibility projections,
and populate `section_path` and `source_locators` from the draft.

- [x] **Step 5: Run normalizer and generic planner tests.**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_document_readers.py \
  tests/test_document_chunking.py \
  tests/test_document_normalizer.py \
  tests/test_metadata_indexer.py -q
```

Expected: unchanged Markdown has deterministic v2 chunks; reader lineage or
chunker changes mark affected documents stale.

### Task 4: Persist generic structure and feed projections

**Files:**

- Modify: `src/vault_graph/ingestion/document_normalizer.py`
- Modify: `src/vault_graph/storage/interfaces/metadata_store.py`
- Modify: `src/vault_graph/storage/local/sqlite_metadata_store.py`
- Modify: `src/vault_graph/indexing/metadata_indexer.py`
- Modify: `src/vault_graph/indexing/vector_indexer.py`
- Modify: `src/vault_graph/storage/local/sqlite_keyword_index.py`
- Modify: `src/vault_graph/app/local_index_service_factory.py`
- Modify: `tests/test_metadata_chunk_listing.py`
- Modify: `tests/test_metadata_evidence_resolution.py`
- Modify: `tests/test_sqlite_metadata_store.py`
- Modify: `tests/test_vector_indexer.py`

- [x] **Step 1: Add backward-compatible model fields.**

Add `format`, `reader_name`, `reader_version`, and
`extraction_options_digest` to `DocumentSnapshot` with safe defaults where
existing fakes require them. Add the same lineage fields to `DocumentState` so
freshness comparison can see reader changes. Add `section_path` and
`source_locators: tuple[SourceLocator, ...] = ()` at the end of
`ChunkSnapshot` and `EvidenceReference`, plus
`document_order: int = 0` at the end of `ChunkSnapshot`, so current
constructors remain valid. `document_order` is traversal metadata only and must
never participate in `chunk_id`.

- [x] **Step 2: Add and migrate the metadata-v3 schema.**

Change `SCHEMA_VERSION` to `metadata-v3`. Add the document lineage columns and
the chunk columns:

```sql
section_path_json TEXT NOT NULL DEFAULT '[]',
source_locators_json TEXT NOT NULL DEFAULT '[]',
document_order INTEGER NOT NULL DEFAULT 0
```

Use an initialization-only upgrade helper that checks `PRAGMA table_info` and
adds missing columns. Read-only opens must not run the helper; health output
must identify incompatibility and recommend `vg index`.

- [x] **Step 3: Round-trip and validate structure/locators.**

Serialize section paths as JSON lists of strings and locators as a deterministic
list of objects containing `scheme`, `coordinates`, offsets, and offset unit.
Validate every decoded value before returning a chunk or evidence reference.
Malformed data must produce `MetadataStoreError` or an incompatible health
result, never a silently incomplete locator.

Update `list_document_chunks(...)` to order by `document_order` and
`chunk_id`, and update the normalizer/draft conversion so document order is
assigned from the reader's forward unit sequence. Keep the order out of stable
identity calculations.

Update `_document_changed` in `metadata_indexer.py` to compare format, reader
name/version, extraction-options digest, parser version, and chunker version.
Add a focused test proving a reader-version or extraction-option change marks a
document stale even when its extracted text and raw source hash are unchanged.

Cover:

```python
def test_section_path_and_locators_round_trip(tmp_path: Path) -> None:
    store = make_initialized_metadata_store(tmp_path)
    store.apply_metadata_revision(documents=(document,), chunks=(chunk,), tombstones=())
    restored = store.resolve_chunk(vault_id=chunk.vault_id, chunk_id=chunk.chunk_id)
    assert restored is not None
    assert restored.section_path == ("Architecture", "Retrieval")
    assert restored.source_locators == chunk.source_locators


def test_existing_metadata_schema_gains_v3_columns_on_initialized_open(tmp_path: Path) -> None:
    create_metadata_v2_fixture(tmp_path)
    store = make_initialized_metadata_store(tmp_path)
    assert "section_path_json" in store.health().message or store.health().schema_compatible


def test_malformed_locator_json_is_not_returned_as_evidence(tmp_path: Path) -> None:
    store = make_initialized_metadata_store(tmp_path)
    corrupt_source_locator_json(store)
    with pytest.raises(MetadataStoreError):
        store.list_chunks(scope)
```

- [x] **Step 4: Change derived projections only.**

In `_embed_chunks`, send `contextual_embedding_text(...)` to
`TextEmbeddings`, but keep the raw chunk hash as `source_chunk_hash` and keep
synthetic context out of metadata blobs. In FTS5, index
`" > ".join(chunk.section_path) or chunk.section or ""`; retain the existing
leaf `section` in user-facing evidence.

Import `CHUNKER_VERSION` into the component-manifest writer instead of
publishing a hard-coded normalizer label.

- [x] **Step 5: Run metadata, vector, graph, and retrieval contract tests.**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_metadata_chunk_listing.py \
  tests/test_metadata_evidence_resolution.py \
  tests/test_sqlite_metadata_store.py \
  tests/test_sqlite_keyword_index.py \
  tests/test_vector_indexer.py \
  tests/test_index_service_vector_reconcile.py \
  tests/test_graph_indexer.py -q
```

Expected: ancestor section search works, format-specific locators resolve, raw
evidence is unchanged, document chunks are ordered deterministically, and the
old chunker version is reconciled only inside the selected scope.

### Task 5: Add final parent/neighbor context expansion as an independent policy

**Files:**

- Create: `src/vault_graph/retrieval/context_expansion.py`
- Create: `tests/test_context_expansion.py`
- Modify: `src/vault_graph/storage/interfaces/metadata_store.py`
- Modify: `src/vault_graph/retrieval/retrieval_result.py`
- Modify: `src/vault_graph/retrieval/retrieval_service.py`
- Modify: `tests/test_retrieval_service_search.py`

- [x] **Step 1: Write context-policy contract tests against an in-memory fake.**

Create four ordered chunks in one document with section paths
`("A",)`, `("A",)`, `("A", "B")`, and `("C",)`. Assert:

```python
expansion = ContextExpander(metadata_store=fake_store).expand(
    matched_chunk=chunks[2],
    scope=scope_for("vault-a", "docs"),
    max_tokens=20,
    neighbor_radius=1,
)
assert expansion.matched_chunk_id == chunks[2].chunk_id
assert chunks[1].chunk_id in expansion.context_chunk_ids
assert expansion.parent_section_path == ("A",)
assert expansion.policy_version == "parent-neighbor-v1"
```

Add a second test with the matching neighbor in another Vault and a third test
with a context budget too small for the next chunk. The first must never return
the other Vault's chunk; the second must return a bounded warning rather than
exceeding the budget.

- [x] **Step 2: Run the context tests and verify failure.**

Run:

```bash
uv run --python 3.12 pytest tests/test_context_expansion.py -q
```

Expected: FAIL because the context policy, ordered metadata lookup, and
result fields do not yet exist.

- [x] **Step 3: Implement the versioned context policy.**

Add `CONTEXT_POLICY_VERSION = "parent-neighbor-v1"` and implement:

```python
class ContextExpander:
    def __init__(self, *, metadata_store: MetadataStore) -> None:
        self._metadata_store = metadata_store

    def expand(
        self,
        *,
        matched_chunk: ChunkSnapshot,
        scope: QueryScope,
        max_tokens: int,
        neighbor_radius: int = 1,
    ) -> ContextExpansion:
        raise NotImplementedError
```

The implementation must list chunks for the matched document through
`MetadataStore`, use `document_order` for neighbors, use the longest common
section-path prefix for the parent section, enforce the requested token budget,
and return warnings when a candidate is missing or omitted. It must validate
that the matched chunk is inside `QueryScope` before expanding. It must never
write to Vault, call `TextEmbeddings`, or create VectorStore records.

- [x] **Step 4: Add the retrieval result fields and integration.**

Add backward-compatible fields to `RetrievalResult`:

```python
matched_chunk_id: str = ""
context_chunk_ids: tuple[str, ...] = ()
context_policy_version: str = "none"
```

After existing candidate fusion and evidence resolution, call
`ContextExpander.expand(...)`. Keep the matched evidence reference in
`RetrievalResult.evidence`; expose only context IDs and policy metadata in the
result. A later context-pack renderer may resolve those IDs through
`MetadataStore` without changing VectorStore records.

Add an optional `context_expander: ContextExpander | None = None` constructor
argument to `RetrievalService`. Update `ReadOnlyServiceFactory` and the direct
CLI construction path to inject `ContextExpander(metadata_store=metadata_store)`;
tests that construct `RetrievalService` without it must retain the backward-
compatible `context_policy_version="none"` behavior.

- [x] **Step 5: Run context and retrieval tests.**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_context_expansion.py \
  tests/test_retrieval_service_search.py \
  tests/test_read_only_service_factory.py \
  tests/test_read_only_boundary.py -q
```

Expected: matched evidence remains authoritative, context expansion respects
Vault/content scope and budget, and changing `CONTEXT_POLICY_VERSION` alone
does not create vector upserts or tombstones.

### Task 6: End-to-end migration and future-adapter contract verification

**Files:**

- Modify only if required by verified behavior: `docs/TODO.md`, `docs/SPEC.md`,
  `docs/SEARCH_ARCHITECTURE.md`
- Modify only if implementation corrected a documented mismatch:
  `docs/PATCH_LOG.md`
- Modify only after user approval of a product or policy choice:
  `docs/DECISIONS.md`

- [x] **Step 1: Run the focused regression suite.**

Run:

```bash
uv run --python 3.12 pytest \
  tests/test_document_readers.py \
  tests/test_document_chunking.py \
  tests/test_vault_loader.py \
  tests/test_document_normalizer.py \
  tests/test_metadata_indexer.py \
  tests/test_metadata_chunk_listing.py \
  tests/test_sqlite_metadata_store.py \
  tests/test_sqlite_keyword_index.py \
  tests/test_vector_indexer.py \
  tests/test_index_service_vector_reconcile.py \
  tests/test_graph_indexer.py \
  tests/test_context_expansion.py \
  tests/test_retrieval_service_search.py \
  tests/test_read_only_service_factory.py \
  tests/test_read_only_boundary.py \
  tests/test_vector_indexing_read_only_boundary.py -q
```

Expected: all focused tests pass and no Vault fixture file is changed.

- [x] **Step 2: Run a dry-run migration against a temporary Markdown Vault.**

Create a temporary Vault containing a nested heading document, a section larger
than the v2 budget, a fenced code block containing lines beginning with `#`, a
Markdown table, and two sibling sections where one is inserted before the
other on a second run. Verify that the second dry run is clean and that a
chunker-version migration reports selected-scope metadata changes, vector
upserts, and old-vector tombstones without writing inside the Vault. The
selected-scope vector reconcile assertion is covered by the focused vector
indexer and index-service tests.

- [x] **Step 3: Run the same planner against synthetic future-reader fixtures.**

Use the fake reader to emit:

- PlainText-style paragraphs with line/character locators;
- PDF-style page/offset locators across two pages;
- DOCX-style heading, paragraph, and table-row locators.

Expected: all three fixtures produce valid bounded chunks, preserve their
locators, and use the same chunk ID and embedding projection functions. No
format-specific code may be added to `document_chunking.py` for this test.

- [x] **Step 4: Run the full quality gates.**

Run:

```bash
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
git diff --check
```

Expected: no lint, type, or whitespace errors.

- [x] **Step 5: Verify recovery and optional-dependency behavior.**

Optional readers are not registered in this slice, so verify the equivalent
boundary: registry construction imports no optional dependency, unsupported
suffixes remain outside the Markdown scan, and extraction warnings are visible
in the metadata plan and CLI output. Dependency-specific `vg status` recovery
remains part of each future reader adapter slice.

## Errors and edge cases

- Empty Markdown produces no chunk drafts and no vector calls.
- A heading-only section produces one context-bearing draft with empty raw body;
  its keyword identity remains the section path.
- A single oversized paragraph, list item, fenced code block, table row, PDF
  text span, or DOCX paragraph must still be split deterministically rather
  than violating the budget.
- An unterminated fenced-code block is retained to end-of-document and emits a
  bounded parser warning; heading markers inside it remain code text.
- A malformed table falls back to an ordinary paragraph block rather than being
  partially interpreted as a table.
- Repeated headings remain distinguishable through deterministic occurrence
  keys; exact duplicate insertion is documented as the unavoidable ambiguity.
- A changed section path or source locator changes the affected metadata
  revision and causes vector reconcile even when the raw body is unchanged.
- A changed context-prefix formatting rule requires a new `CHUNKER_VERSION`.
- An unsupported suffix or missing optional reader dependency produces a clear
  warning and leaves Markdown indexing available.
- A reader that returns malformed locators is rejected before metadata writes;
  it cannot create evidence that cannot be traced back to the source.
- A narrow `QueryScope` tombstones and re-embeds only selected Vault/content
  scopes; records outside the scope remain untouched.
- Context expansion rejects a matched chunk outside `QueryScope`, omits
  neighbors outside the scope, and reports a warning when the context budget
  prevents a requested expansion.
- Changing only `CONTEXT_POLICY_VERSION` changes retrieval metadata but does
  not stale vectors or alter chunk IDs.
- Missing or incompatible metadata-v3 columns fail closed for read-only status
  and search and recover through initialized `vg index`.
- Reader and parser warnings do not write source files and remain visible in
  indexing or status output.
- Vector failure after metadata success leaves metadata applied and vector
  state recoverable, matching the existing cross-store failure contract.

## Validation review

- **Security/read-only:** the parser reads bytes only, never executes fenced
  code, and all writes remain under Vault Graph Data Home. Existing boundary
  tests must continue to pass.
- **Performance/scalability:** reader extraction and shared packing are linear
  in extracted content; non-overlap avoids multiplying vector count; the
  chunker adds no runtime model or network dependency. The first v2 migration
  is expected to re-embed the selected scope once.
- **Testability:** every slice has an independent input and exit condition;
  reader contracts, parser, packer, stable identity, locator round-trip,
  embedding input, keyword projection, stale-vector reconcile, and context
  expansion have separate focused tests. Pure slices use fakes and do not
  require optional readers or a live embedding model.
- **Maintainability:** format-specific parsing and locators stay behind reader
  adapters; window policy lives in one deep ingestion boundary; MetadataStore
  owns raw text/evidence/order; VectorIndexer owns only embedding projection;
  context expansion owns retrieval policy.
- **Agent ergonomics:** section context improves semantic matches without
  polluting returned evidence text, while locators let future PDF/DOCX results
  point back to the original source. Matched/context IDs and policy reasons are
  explicit without changing the leaf vector contract.

## Risks and mitigations

- **Risk:** the estimated token count does not match the FastEmbed tokenizer.
  **Mitigation:** keep the estimator deterministic and model-independent for
  v2, add a fixed Korean/English benchmark, and adjust the versioned default
  before release if actual truncation is observed.
- **Risk:** the common block model becomes a lowest-common-denominator format
  that loses PDF/DOCX evidence detail. **Mitigation:** keep
  `SourceLocator.coordinates` extensible and preserve adapter-specific safe
  units; the common planner combines units but does not flatten locators.
- **Risk:** a structural parser diverges from every Markdown dialect.
  **Mitigation:** constrain v2 to explicit block guarantees, test fences/tables/
  lists/quotes, and defer full CommonMark compatibility until a real Vault
  fixture requires it.
- **Risk:** packing changes cause more re-embedding than expected.
  **Mitigation:** use non-overlapping windows, structural boundary IDs, and
  inspect dry-run upsert/tombstone counts before applying the selected scope.
- **Risk:** context expansion accidentally becomes a second retrieval index or
  crosses scope boundaries. **Mitigation:** derive neighbors only through
  `MetadataStore`, require `QueryScope` validation in `ContextExpander`, and
  keep `CONTEXT_POLICY_VERSION` separate from `CHUNKER_VERSION`.
- **Risk:** adding reader lineage, `section_path_json`, and
  `source_locators_json` creates stale old metadata stores. **Mitigation:**
  initialized opens add defaulted columns; read-only opens fail clearly; the
  first v2 index repopulates selected documents.

## Open Decisions

1. **Final v2 budget.** Recommendation: start with `256` estimated tokens and
   lock the value only after the fixed Korean/English retrieval fixture confirms
   that the current FastEmbed model does not truncate the embedding input. Do
   not expose a user setting until that benchmark shows a need.
2. **Chunker version label.** Recommendation: use the generic
   `document-block-window-v2` label and update the TODO migration name when the
   decision is accepted. If preserving the already documented migration label
   is more important, keep `markdown-block-window-v2` for this release while
   keeping the implementation and fields format-neutral.
3. **Source locator shape.** Recommendation: persist a list of immutable
   locators per chunk rather than one flattened page/line field. This supports
   chunks spanning PDF pages and DOCX tables without losing provenance, while
   the locator `scheme` and coordinates remain adapter-owned.
4. **Markdown dialect coverage.** Recommendation: use the local deterministic
   state machine for v2. Add a parser dependency only if a real Vault fixture
   requires CommonMark/GFM behavior that cannot be implemented as a small,
   deterministic block rule.
5. **Context visibility.** Recommendation: keep section-path context in vector
   and keyword projections only; retain raw extracted evidence text in
   `ChunkSnapshot.text`, and expose source locators as evidence metadata. This
   preserves source fidelity while improving semantic/lexical recall and keeps
   future PDF/DOCX coordinates out of embeddings.
6. **Context policy defaults.** Recommendation: use one previous and one next
   chunk, prefer the nearest common section-path parent, and enforce the
   existing context token budget. Keep expansion out of VectorStore.
7. **Future reader enablement.** Recommendation: keep the registry extensible
   but Markdown-only by default. Enable PlainText first after contract tests;
   enable PDF only once page/text locators are reliable; enable DOCX only once
   style-based heading and paragraph extraction is deterministic.

## Expected outcome

After this plan is implemented, the first `vg index` after the version change
will intentionally re-index and re-embed the selected scope. Subsequent
unchanged runs will converge with zero stale vectors, unrelated sections will
retain their chunk identities, large documents will be bounded, section
context will be available to retrieval, matched results will expose bounded
parent/neighbor context separately, and format-specific locators will be ready
for future PlainText/PDF/DOCX readers without changing the evidence authority
or the leaf retrieval identity.
