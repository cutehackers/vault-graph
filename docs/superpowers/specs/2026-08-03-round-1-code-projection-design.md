# Round 1 Code Projection Design

Status: Draft for review

Date: 2026-08-03

Source contracts:

- [`docs/SPEC.md`](../../SPEC.md) 1.2
- [`docs/DESIGN.md`](../../DESIGN.md)
- [`docs/CONVENTIONS.md`](../../CONVENTIONS.md)
- [`docs/DECISIONS.md`](../../DECISIONS.md)
- [`2026-08-03-round-0-g-authority-projection-hygiene-design.md`](2026-08-03-round-0-g-authority-projection-hygiene-design.md)
- [`2026-07-30-code-index-agent-context-direction-report-ko.md`](../reports/2026-07-30-code-index-agent-context-direction-report-ko.md)

External references consulted:

- [CodeGraph introduction](https://colbymchenry.github.io/codegraph/getting-started/introduction/)
- [CodeGraph how it works](https://colbymchenry.github.io/codegraph/core-concepts/how-it-works/)
- [CodeGraph README](https://github.com/colbymchenry/codegraph/blob/main/README.md)

This document is subordinate to `docs/SPEC.md`. It makes the already accepted
Round 1 direction implementation-ready; it does not change the active product
identity until the design is approved and implemented.

## 1. Goal

Round 1 adds a deterministic, local-first code projection for explicitly
registered source repositories. The projection lets humans and agents inspect
symbols, imports, calls, inheritance, tests, and change impact without copying
the repository into Vault or treating derived graph state as executable source.

The design takes the most useful CodeGraph ideas—Tree-sitter extraction, a
staged extraction/resolution pipeline, local SQLite graph queries, incremental
change detection, and visible freshness warnings—and adapts them to Vault
Graph's authority and projection contracts.

The Round 1 result is a reusable code application service and a small CLI
diagnostic surface. Round 2 will compose it with Vault evidence behind a
single project-context MCP entry point.

## 2. Scope

### 2.1 In scope

- read-only registration of source-repository roots
- duplicate and overlapping-root validation
- deterministic Python and Dart structure extraction
- file, module, class, interface/mixin, function, method, property, and test
  symbol records where the language adapter can identify them
- `CONTAINS`, `DEFINES`, `IMPORTS`, `CALLS`, `EXTENDS`, `IMPLEMENTS`, and
  `TESTS` relationships
- repository-scoped symbol identity and line-range evidence
- local SQLite code projection with FTS5 symbol/path search
- deterministic reference resolution and unresolved-reference retry
- full rebuild and incremental reconcile, including deleted files
- optional local file watching with debounce
- source revision and working-tree freshness reporting
- `fresh`, `stale`, `syncing`, `partial`, `unavailable`, and `unknown` states
- read-only structural CLI queries for search, symbol, callers, callees, and
  impact
- projection manifests, run diagnostics, and atomic activation
- tests proving read-only behavior, deterministic rebuilds, identity stability,
  freshness warnings, and duplicate-edge prevention

### 2.2 Out of scope

- changing, formatting, renaming, deleting, or committing repository files
- writing code or automatically applying refactors
- publishing code or generated context into Vault
- merging Vault documents and code symbols into one authority record
- LLM-generated code relationships or autonomous truth arbitration
- semantic code embeddings, vector search, or reranking
- broad language coverage beyond the first Python and Dart adapters
- visual graph dashboards or PR review automation
- Round 2 `ProjectContextService`, `explore_project`, or MCP harness guidance
- hosted databases, remote indexing, or mandatory SaaS services

## 3. Authority, duplication, and safety contract

### 3.1 Two source authorities

Vault remains authoritative for durable project knowledge. Each registered
source repository remains authoritative for its current executable code.
Vault Graph reads both authorities and writes only to its configured state
directory. A code projection is a disposable evidence view, never a source
repository or a durable Vault page.

Vault documents and repository symbols that use the same name remain separate
records. A future cross-source relationship may connect them, but it must carry
both source identities and an explicit extraction status. Round 1 does not
create those cross-source links.

### 3.2 Repository owns code plaintext

The repository is the only persistent owner of code source bodies. The code
projection stores no complete file body, source excerpt, or generated summary.
It stores bounded structural metadata:

- repository and relative file identity
- content hash and source revision
- symbol name, qualified name, kind, signature, and line range
- relationship endpoints, relation kind, anchor range, and extraction status
- searchable symbol/path metadata

When a query needs source text, `CodeQueryService` reads the requested bounded
line range from the registered repository through the read-only path guard. It
checks the current file hash against the indexed hash and emits a freshness
warning if the source changed during or after indexing.

This preserves the Round 0-G single-body rule across authorities. Physical
deduplication of metadata is allowed only when it does not erase repository
namespace, path, revision, line range, parser version, or evidence identity.

### 3.3 Allowed writes

Round 1 may write only to the configured Vault Graph state/configuration:

- repository catalog configuration explicitly managed by a Vault Graph command
- `data/code/` or the configured equivalent
- projection generations, manifests, status, and run diagnostics

It must never write to:

- Vault `raw/`, `wiki/`, `docs/`, or `scratch/`
- a registered repository's source, tests, manifests, or Git metadata
- an arbitrary path supplied through an unvalidated repository entry

## 4. CodeGraph lessons and Vault Graph adaptations

| CodeGraph strength | Round 1 adoption | Vault Graph boundary |
| --- | --- | --- |
| Tree-sitter structural extraction | A pinned Python/Dart parser adapter contract | Parser output is derived evidence, not source authority |
| Files → extraction → database → resolution → graph queries | One staged `CodeProjectionService` pipeline | Each stage has a typed interface and isolated failure state |
| Local SQLite and FTS5 | Repository-scoped code store and symbol/path FTS | FTS contains structural fields, never complete source bodies |
| Import/call/inheritance resolution | Deterministic resolver plus pending-reference retry | Dynamic or ambiguous edges remain labeled and are never guessed as certain |
| Native watcher and incremental sync | Optional local watcher with debounce and hash reconciliation | Watcher is read-only, opt-in, and never hides pending changes |
| One exploration result with exact source lines | Round 1 CLI returns bounded line evidence per structural query | Unified Vault + code exploration is deferred to Round 2 MCP |
| Stale-file warnings | Every query reports projection/source freshness and affected paths | `unknown` is not treated as `fresh` |
| Partial-index visibility | Interrupted or incomplete runs activate no partial generation | Previous active generation remains readable after failure |

CodeGraph's product surface and bundled runtime are not copied. Vault Graph
keeps its Python package, local-first dependencies, source-authority rules, and
existing application-service boundaries.

### 4.1 Parser backend decision

`CodeParserAdapter` is a Python protocol and normalization boundary. It does
not mean that Vault Graph should implement the Python or Dart grammar itself,
nor that the indexer should execute Dart code. The Round 1 baseline uses
Python wrappers around a proven Tree-sitter runtime:

- `tree-sitter` Python bindings for the parser runtime
- a pinned Python grammar package
- a pinned Dart grammar artifact with an explicit ABI and grammar revision
- Python-owned language query/extraction code that maps parser nodes into the
  common Vault Graph symbol and reference DTOs

This is the best initial fit for Vault Graph because it keeps one local runtime,
supports incremental/error-tolerant syntax parsing, avoids requiring a Dart SDK
or analysis server, and makes repeated rebuilds testable under one parser
contract. The current repository does not yet ship Tree-sitter dependencies;
implementation must add and pin them rather than relying on an ambient parser
installation.

Dart's official `analyzer` package remains a future optional semantic resolver,
not a Round 1 baseline. It can provide higher-fidelity type and package
resolution, but it couples indexing to Dart SDK/package configuration and an
additional runtime. If enabled later, its edges must be labeled with a
separate resolver version and may enrich—not replace—the deterministic
Tree-sitter projection.

The Dart grammar must pass a fixture gate for classes, mixins, extensions,
imports, async functions, named/optional parameters, annotations, and test
files. Unsupported constructs produce explicit diagnostics and `partial`
freshness; they do not become guessed relationships.

## 5. Architecture

```text
RepositoryCatalog
       |
       v
CodeProjectionService
  scan/fingerprint -> parse -> persist -> resolve -> audit -> activate
       |
       +--> CodeParserAdapter (Python, Dart)
       +--> SymbolResolver
       +--> CodeProjectionStore (SQLite + FTS5)
       +--> CodeFreshnessService
       +--> CodeQueryService
       |
       v
CLI: repository / index / status / search / symbol / callers / callees / impact
       |
       v
Round 2: ProjectContextService -> MCP explore_project
```

Each component is a deep module with a small protocol:

### 5.1 `RepositoryCatalog`

Owns repository registration, canonical path validation, include/exclude
policy, language policy, state namespace, and watch policy. It is the only
component that maps a stable `repository_id` to a root path.

It does not inspect ASTs, persist symbols, or resolve calls. It rejects
duplicate IDs, duplicate canonical roots, and overlapping roots unless a
future explicit nested-repository policy allows the relationship.

### 5.2 `CodeProjectionService`

Owns the full and incremental application workflows. It accepts a repository
scope and run mode, calls the scanner/parser/resolver/store protocols, and
returns a typed run report. CLI and future MCP adapters call this service and
never open SQLite tables directly.

### 5.3 `CodeParserAdapter`

Hides Tree-sitter nodes, grammar queries, and language-specific AST details.
Each Python implementation returns normalized file, symbol, and raw-reference
records. The first adapters are Python and Dart with pinned grammar/parser
specification versions. Syntax errors produce file-scoped diagnostics and
partial extraction where safe; they do not permit the adapter to invent
symbols.

### 5.4 `SymbolResolver`

Resolves imports, calls, inheritance, implementation, and test targets against
the staged symbol snapshot. Resolution is deterministic and repository-scoped.
Unresolved references are retained in a pending table with enough source
identity to retry when a later change introduces a matching definition.

Dynamic dispatch, callback paths, and framework conventions may be represented
as `inferred` only when a deterministic rule identifies the endpoints. Otherwise
the relationship remains `ambiguous` or `unresolved` and is excluded from
default impact results.

### 5.5 `CodeProjectionStore`

Owns the local code projection schema, manifests, run diagnostics, structural
records, and FTS candidate lookup. It does not own source file bodies and does
not expose backend-specific rows to callers.

### 5.6 `CodeFreshnessService`

Compares the live repository snapshot with the active code manifest. It owns
working-tree detection, pending-path classification, run state, and warning
construction. It may use Git metadata according to the repository's declared
revision policy, but a missing Git repository does not prevent content-hash
freshness checks.

### 5.7 `CodeQueryService`

Provides structural query DTOs and resolves bounded source evidence at read
time. It owns deterministic ordering, depth/limit enforcement, stale warnings,
and exclusion of unresolved edges from confident results. The CLI and Round 2
context service depend on this interface.

## 6. Repository registration model

The catalog entry is the minimum configuration needed to read one source
repository:

```yaml
repository_id: vault-graph
root_path: /absolute/path/to/repository
display_name: Vault Graph
enabled: true
include_globs: ["src/**", "tests/**"]
exclude_globs: [".git/**", ".venv/**", "build/**", ".dart_tool/**"]
languages: [python, dart]
state_namespace: vault-graph
git_revision_policy: head-and-working-tree
watch: false
```

The catalog normalizes `root_path` with `expanduser().resolve()` and rejects:

- missing or non-directory roots
- duplicate `repository_id`
- two entries with the same canonical root
- a root nested under another registered root, or a parent containing another
  registered root, unless both entries explicitly identify independent nested
  repositories in a future policy
- symlinked include paths that resolve outside the repository root
- empty or path-traversing include/exclude patterns

The default exclusion policy ignores VCS metadata, virtual environments,
package caches, build artifacts, generated output, and vendored dependencies.
Users may opt a path back in explicitly. The scanner records the applied policy
in every run manifest so equivalent rebuilds use equivalent input.

Repository identity is not `vault_id`. A project may pair one `repository_id`
with one or more Vault IDs later, but Round 1 keeps catalog namespaces
independent.

## 7. Extraction and symbol contract

### 7.1 Normalized file snapshot

```text
CodeFileSnapshot
  repository_id
  relative_path
  language
  content_hash
  byte_count
  line_count
  source_revision
  is_test_file
  parser_spec_version
```

The scanner reads bytes once per file for hashing and parsing. The source
revision includes the configured Git revision and a deterministic working-tree
snapshot hash when uncommitted edits exist. A file with the same content hash,
parser spec, and include policy is unchanged even if Git still reports it as
untracked.

### 7.2 Symbol kinds

The common vocabulary is intentionally small:

- `repository`
- `file`
- `module`
- `class`
- `interface`
- `mixin`
- `function`
- `method`
- `property`
- `test`

Adapters may map a language-specific declaration to the nearest common kind and
keep the original language-specific label in `language_kind`. A declaration
that cannot be mapped is retained as a file-level diagnostic rather than
silently dropped.

### 7.3 Relationship kinds

Round 1 supports:

- `CONTAINS`: repository/file/module/class contains a child
- `DEFINES`: a file or module defines a symbol
- `IMPORTS`: a file/module imports another file or module
- `CALLS`: a function/method calls a resolved function/method
- `EXTENDS`: a class extends a base class
- `IMPLEMENTS`: a class implements an interface/mixin contract
- `TESTS`: a test symbol targets a production symbol or file

Each edge records `extraction_status` as `extracted`, `inferred`, `ambiguous`,
or `unresolved`. Only `extracted` and explicitly requested `inferred` edges
participate in default structural traversal. `ambiguous` and `unresolved`
records remain inspectable diagnostics.

## 8. Stable identity and evidence

Identity is repository-scoped and independent of mutable line numbers:

```text
file_id = sha256("code-file-v1", repository_id, relative_path)

symbol_id = sha256(
  "code-symbol-v1",
  repository_id,
  file_id,
  symbol_kind,
  qualified_name,
  declaration_disambiguator,
)

edge_id = sha256(
  "code-edge-v1",
  repository_id,
  source_symbol_id,
  relation_kind,
  target_symbol_id or unresolved_target_key,
  anchor_start_line,
  anchor_start_column,
  extractor_spec_version,
)
```

The declaration disambiguator is deterministic for same-name declarations in a
file, such as an ordinal among declarations with the same qualified name and
kind. A rename creates a new symbol identity; a line shift does not. A changed
body preserves symbol identity while updating the file hash, line range, and
source revision.

Every user-visible `CodeEvidence` carries:

- `repository_id`
- `file_id` and relative path
- `symbol_id` when applicable
- line and column range
- indexed content hash and current content hash when read
- indexed source revision and current source revision when known
- parser/extractor spec version
- evidence kind and retrieval reason
- freshness warnings

Vault `document_id`, `chunk_id`, `provenance_family_id`, and code `symbol_id`
are never interchangeable.

## 9. Storage contract

The local schema is `code-projection-v1` and is stored under a staged generation
inside the configured Graph state directory:

```text
projections/generations/<generation_id>/code/
  code.sqlite3
  status.json
```

Logical tables:

```text
repositories
files
symbols
edges
pending_references
symbol_fts
projection_runs
file_fingerprints
```

Required invariants:

- `repository_id + relative_path` is unique within `files`
- `symbol_id` is globally unique by derivation but always stores
  `repository_id`
- `(source_symbol_id, relation_kind, target_symbol_id, anchor)` has one edge
- every resolved endpoint belongs to the same repository
- every file and symbol evidence range points to an indexed file snapshot
- FTS rows contain path, qualified name, signature, language, and symbol kind;
  no complete file body or excerpt is stored
- pending references cannot be returned as resolved graph edges
- a generation is readable only after its manifest and health checks pass

The store exposes protocols, not SQL tables:

```python
class CodeProjectionStore(Protocol):
    def health(self) -> StoreHealth: ...
    def current_manifest(self, repository_ids: tuple[str, ...]) -> CodeManifest: ...
    def apply_reconcile_plan(self, plan: CodeReconcilePlan) -> CodeApplyResult: ...
    def search_symbols(self, query: CodeSymbolQuery) -> tuple[CodeSymbolHit, ...]: ...
    def get_symbol(self, symbol_id: str) -> CodeSymbolRecord | None: ...
    def traverse(self, query: CodeTraversalQuery) -> CodeTraversalResult: ...
```

Round 1 does not add vector or embedding columns. A later semantic projection
must be separately versioned and must not weaken the reference-only body rule.

## 10. Projection pipeline

### 10.1 Full rebuild

1. Resolve enabled repository entries and validate their roots.
2. Scan files using the catalog's include/exclude and language policy.
3. Compute deterministic file fingerprints and source revision metadata.
4. Parse changed files through the language adapters.
5. Stage files, symbols, `CONTAINS`, `DEFINES`, and raw references.
6. Resolve imports, calls, inheritance, implementation, and test targets.
7. Persist unresolved references and run deterministic duplicate-edge checks.
8. Run health, schema, source-boundary, and dangling-reference audits.
9. Atomically activate the new code generation and record the run report.

If any global step fails, the old active generation remains active. A failed
staging directory may be removed only after the failure report is durable in
Graph state; no repository file is touched.

### 10.2 Incremental reconcile

An incremental run compares current fingerprints with the active manifest and
classifies paths as added, modified, deleted, unchanged, or pending. It parses
only changed files plus files whose unresolved or dependent references must be
revisited. It then:

- removes deleted-file symbols and edges
- replaces modified-file records as one file-level unit
- retries references whose target namespace could have changed
- leaves records outside the selected repository scope untouched
- emits counts for scanned, parsed, resolved, retried, deleted, skipped, and
  pending paths

The incremental result must be functionally equivalent to a full rebuild from
the same source snapshot after normalizing run IDs, timestamps, and generation
paths.

### 10.3 Watch mode

Watch mode is an optional read-only service. Native file events are debounced,
filtered through the catalog policy, and converted into the same incremental
reconcile request. A watcher never writes source files, changes Git state, or
claims freshness before the reconcile succeeds. A crash or interrupted run
leaves the active generation unchanged and reports `partial` for the attempted
run.

## 11. Freshness and run states

The code projection distinguishes source state from projection state:

| State | Meaning | Query behavior |
| --- | --- | --- |
| `fresh` | All selected paths match the active manifest and compatible parser/schema specs | Normal results; no freshness warning |
| `stale` | At least one selected path differs or is pending | Results may be returned with affected-path warning |
| `syncing` | An incremental run is in progress | Return active generation plus syncing warning |
| `partial` | Last run did not reconcile the discovered input set completely | Return active generation plus partial warning; never label fresh |
| `unavailable` | No compatible active generation or store health failure | Structural queries fail with recovery guidance |
| `unknown` | Source or revision could not be inspected safely | Return results only with explicit unknown warning |

Freshness is computed from:

- current file content hash and indexed content hash
- include/exclude and language policy hash
- parser/extractor specification versions
- code schema version
- source revision policy
- pending/deleted path set

Git `HEAD` alone is insufficient when the working tree is dirty. The working
tree snapshot is therefore represented separately. A missing Git binary or
non-Git repository falls back to content hashes and reports revision kind
`content-hash`.

## 12. Query service and CLI contract

### 12.1 `CodeQueryService`

The initial service methods are:

- `search_symbols(query, repository_ids, kinds, path_prefix, limit)`
- `get_symbol(symbol_id, include_source=True, max_lines=...)`
- `get_file_outline(repository_id, relative_path)`
- `get_callers(symbol_id, depth=1, limit=...)`
- `get_callees(symbol_id, depth=1, limit=...)`
- `get_impact(symbol_id, direction="inbound", depth=3, limit=...)`

Traversal is cycle-safe, depth-bounded, and deterministically ordered by
distance, extraction status, repository ID, path, line, and symbol ID. Results
do not cross repository namespaces implicitly. Unresolved and ambiguous edges
are returned in diagnostics, not counted as certain impact.

Source inclusion is bounded and late-bound: the query resolves the current
repository lines only after selecting structural evidence. If the file hash
has changed, the response includes `source_changed_since_index` and identifies
the exact path; it does not silently present the old line range as current.

### 12.2 CLI

Round 1 adds a diagnostic surface without adding MCP:

```text
vg code repository add ID --path PATH [--language python|dart ...]
vg code repository list
vg code repository remove ID
vg code index [--repository-id ID] [--full] [--dry-run]
vg code status [--repository-id ID] [--verify]
vg code search QUERY [--repository-id ID] [--kind KIND] [--limit N]
vg code symbol SYMBOL_OR_ID [--source]
vg code callers SYMBOL_OR_ID [--depth N]
vg code callees SYMBOL_OR_ID [--depth N]
vg code impact SYMBOL_OR_ID [--depth N]
vg code watch [--repository-id ID]
```

The commands call application services, render JSON/text, and return nonzero
codes for invalid catalogs, unavailable projections, or failed runs. `--dry-run`
does not create a generation, SQLite schema, watcher, or parser cache.

`vg code repository remove` removes the catalog entry and its derived code
projection namespace only after an explicit command. It never removes the
repository directory.

Round 2 may expose the same service through `explore_project`, but it must not
duplicate these query algorithms in the MCP adapter.

## 13. Errors and edge cases

- **Invalid root:** reject registration with a clear path recovery hint.
- **Duplicate/overlapping root:** reject before indexing; identify both entries.
- **Symlink escape:** reject the file and emit a catalog/path warning.
- **Unsupported language:** skip the file with `unsupported_language`; do not
  claim that the repository is fully indexed.
- **Syntax error:** preserve file fingerprint, emit a file-scoped parse warning,
  and retain only safe declarations. The run may be `partial`.
- **Dynamic call:** leave the edge `ambiguous` or `unresolved`; never invent a
  certain target from name similarity alone.
- **Changed during parse:** discard the affected file result and retry once;
  if it still changes, publish the prior active generation with `stale` or
  `partial` status.
- **Deleted file:** tombstone its symbols and incident edges in the staged
  generation.
- **Untracked file:** identify it by content hash and path; do not re-index it
  repeatedly when its content is unchanged.
- **Interrupted run:** preserve the old active generation and record a partial
  run marker.
- **Missing source at query time:** return structural identity and a
  `source_unavailable` warning; do not use stored excerpts because none exist.
- **Schema/parser mismatch:** fail closed for the selected generation and give
  `vg code index --full` as recovery guidance.
- **Cross-repository target:** keep the edge unresolved unless an explicit
  future cross-repository contract exists.

## 14. Verification and tests

### 14.1 Focused tests

- catalog normalization, duplicate IDs, duplicate roots, parent/child roots,
  symlink escapes, and include/exclude policy hashing
- Python and Dart parser fixtures for every common symbol and relationship kind
- stable file/symbol/edge identities across line shifts and body changes
- deterministic parser output and deterministic relationship ordering
- duplicate edge prevention and repository namespace isolation
- import/call/inheritance/test resolution, unresolved retry, and ambiguous-edge
  exclusion from confident impact
- content hash and working-tree freshness detection
- full rebuild vs incremental reconcile equivalence, including deletions and
  untracked files
- interrupted/partial run rollback and active-manifest path safety
- SQLite schema contains no complete source body or excerpt owner
- bounded source read and source-changed warning behavior
- read-only fingerprints proving repositories, Vault, and Git metadata are not
  modified by indexing, status, search, or query commands
- CLI output, exit codes, dry-run no-write behavior, and status state mapping
- watcher debounce and no-write boundary when watcher is enabled

### 14.2 Round 1 completion gate

Round 1 is complete only when:

1. A repository can be registered and invalid/overlapping registrations are
   rejected deterministically.
2. Python and Dart fixtures produce the same normalized graph on repeated runs.
3. Full rebuild and incremental reconcile produce equivalent results for the
   same source snapshot, including added, modified, and deleted files.
4. Every returned symbol/edge has repository, path, line range, content hash,
   revision, and parser/extraction provenance.
5. No complete repository source body or excerpt is persisted in the code
   projection.
6. Duplicate edges and dangling resolved endpoints are zero after a successful
   audit.
7. Stale, partial, unavailable, and unknown states are visible and are never
   reported as `fresh`.
8. Structural queries return bounded current source evidence or an explicit
   source/freshness warning.
9. Repository, Vault, and Git metadata fingerprints are unchanged after every
   indexing/query test.
10. The CLI diagnostic surface passes acceptance tests without requiring MCP,
    embeddings, network access, or hosted services.

### 14.3 Verification commands

The implementation plan must run at least:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv build
git diff --check
```

The acceptance fixture must run a full build, mutate a copy of a source file,
run an incremental build, delete a file, run another incremental build, and
compare the normalized result with a fresh full build. It must also inspect the
SQLite schema/content for forbidden source-body columns and compare repository
fingerprints before and after.

## 15. Performance and scalability posture

Round 1 optimizes for predictable local behavior, not a premature hosted SLA.
The implementation must record these run metrics:

- files discovered, parsed, skipped, deleted, and retried
- symbols and edges extracted, resolved, ambiguous, and unresolved
- full vs incremental mode
- scan, parse, persist, resolve, and activation durations
- pending path count and freshness state
- query candidate count, traversal depth, result count, and source-read time

The benchmark fixture should compare a full run with one-file and multi-file
incremental runs. A numeric latency/throughput budget is intentionally kept as
an open product decision until this baseline exists. The projection interfaces
must nevertheless permit later parser workers, shared watcher daemons, or
scale-up stores without changing CLI/query DTOs.

## 16. Round 2 handoff

Round 2 consumes only `CodeQueryService` and Vault application-service
interfaces. It adds:

- `ProjectContextService`
- one high-level `explore_project(task, project_path=None, max_tokens=None)` MCP
  tool
- code + Vault evidence selection and token budgeting
- project/Vault scope auto-resolution
- harness instructions and explicit install/remove behavior
- benchmark comparison against multi-call search/read workflows

Round 2 must not make the code projection store a second source body, move
parser logic into MCP, or make user prompts write repository/Vault files.

## 17. Open decisions for review

The design makes the following recommendations but leaves them visible for
approval before implementation:

1. **Watcher default:** keep it disabled by default and opt in with
   `vg code watch`; this avoids background work while preserving the CodeGraph
   freshness advantage.
2. **Parser packaging:** pin Tree-sitter core and Python/Dart grammar artifacts
   in the Python distribution, record their ABI/spec versions, and do not
   shell out to language-specific external analyzers in the default path. A
   Dart Analyzer bridge remains an optional later semantic resolver.
3. **Performance budget:** establish a fixture baseline first, then set p95
   query and incremental-sync targets in the Round 1 completion report.
4. **Configuration location:** use a Graph-owned repository catalog file and
   state namespace; never add registration metadata to Vault or the registered
   source repository.

No decision permits source mutation, Vault publication, hidden network access,
or unlabelled inferred relationships.
