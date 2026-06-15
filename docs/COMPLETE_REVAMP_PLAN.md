# Game Library Manager: Complete Revamp Plan

> **Status:** In progress — Milestone 1
> **Prepared:** 2026-06-14  
> **Scope:** Product, UX, architecture, data, reliability, testing, delivery, and documentation  
> **Planning horizon:** 8 milestones / approximately 16–22 focused engineering weeks  
> **Primary constraint:** Preserve existing user libraries and core Windows shortcut workflows throughout the revamp.

## 1. Executive decision

The next release should be treated as a **staged product rewrite inside the existing repository**, not as either a cosmetic redesign or a greenfield replacement.

The application already contains substantial value: shortcut discovery, metadata, collections, update checks, health checks, F95 integration, downloads, archives, themes, and a virtualized grid. Rebuilding all of that at once would create unnecessary migration and regression risk. Conversely, continuing to add features to the current `MainWindow` mixin graph, mutable dataclasses, and direct JSON persistence would make every future feature slower and less reliable.

The recommended strategy is therefore:

1. **Freeze feature expansion and establish measured baselines.**
2. **Create a versioned, atomic persistence boundary and explicit domain model.**
3. **Introduce use-case/application services that own mutations and background jobs.**
4. **Replace the mixin-composed window incrementally with view controllers and Qt models.**
5. **Deliver the redesigned shell and workflows against those stable boundaries.**
6. **Consolidate acquisition/download/archive functionality behind one job system.**
7. **Harden, package, migrate, and release only after objective quality gates pass.**

This sequence deliberately puts data safety and behavioral seams before visual work. The redesign can then proceed quickly without binding new UI code to old state-management patterns.

---

## 2. Product definition

### 2.1 Product promise

**Game Library Manager is a local-first Windows desktop application that discovers, organizes, launches, maintains, and updates large game libraries without taking ownership away from the user.**

### 2.2 Primary users

| Persona | Need | Revamp response |
|---|---|---|
| Large-library curator | Find and maintain hundreds or thousands of entries quickly | Fast model/view library, saved views, bulk operations, keyboard-first navigation |
| Shortcut-based player | Launch reliably despite moved or stale targets | Explicit launch profiles, health diagnosis, guided repair |
| Update tracker | Know what changed and why | Unified source state, durable check history, explainable comparisons |
| Archive/download manager | Acquire, validate, extract, and install safely | One resumable job pipeline with clear provenance and recovery |
| Privacy-conscious local user | Keep control of files, credentials, and metadata | Local-first storage, explicit network actions, OS-backed secrets, export/backup |

### 2.3 Jobs to be done

1. Import an existing library without losing edits.
2. Find any game in under a few seconds.
3. Understand whether a game can launch, has an update, or needs repair.
4. Perform safe bulk organization and maintenance.
5. Download and install an update with visible, recoverable steps.
6. Back up, export, restore, and move the library confidently.

### 2.4 Scope boundaries

**In scope**

- Windows 10/11 desktop experience.
- `.lnk`, `.url`, and `.html` discovery and launch workflows.
- Local metadata, collections, saved views, update state, health state, jobs, archives, and supported source integrations.
- Accessibility, keyboard operation, observability, packaging, migration, and recovery.

**Not in the first revamp release**

- Cloud account or cross-device sync.
- Storefront replacement, social network, or public catalog service.
- Arbitrary third-party plugin execution.
- Automated purchasing or DRM circumvention.
- A second desktop framework. PySide6 remains the UI technology for this program.

---

## 3. Current-state assessment

### 3.1 What should be retained

- The local-first desktop model and Windows-specific shortcut support.
- The existing feature vocabulary: Library, Collections, Updates, Health, Downloads, and Details.
- Pure or mostly pure logic that is already testable, especially title matching, filtering, version parsing, collection evaluation, and F95 parsing.
- The repository abstraction, typed configuration direction, event vocabulary, custom exceptions, logging helpers, background icon loading, and virtualized browsing work.
- Backward-compatible loading behavior and the user's existing `library.json` as an import source.

### 3.2 Structural findings

| Area | Current observation | Consequence | Priority |
|---|---|---|---|
| UI composition | `MainWindow` combines nine behavior mixins and still builds much of the UI itself | Hidden dependencies through `self`, difficult isolated tests, fragile lifecycle ordering | Critical |
| Grid implementation | `grid.py` is over 1,100 lines and manually manages virtualization, pagination, widget pools, animation, and selection | High regression surface and too many responsibilities | High |
| Card/theme implementation | Card and theme modules are each around 870 lines | Visual changes require risky edits to monoliths | High |
| Domain model | One mutable `Game` dataclass carries discovery, launch, source, download, install, archive, backup, and presentation-cache fields | Unclear invariants, accidental coupling, migrations become harder | Critical |
| Persistence | Full library and settings are rewritten directly as formatted JSON | No atomic replace, schema migration registry, transaction boundary, durable history, or corruption recovery | Critical |
| Repository semantics | Repository returns its mutable internal list and UI also keeps aliases to its index/list | Callers can bypass invariants and persistence without detection | Critical |
| Application state | A typed config coexists with compatibility dictionary access and many window-owned mutable fields | Multiple sources of truth and difficult state restoration | High |
| Events | Synchronous callback bus catches broad exceptions and has untyped payloads | Failures can be logged but state transitions are not explicit or replayable | Medium |
| Acquisition stack | Legacy download manager, enhanced service, smart-download coordinator, host handlers, and archive services overlap | Duplicate concepts, uncertain ownership, inconsistent error/retry behavior | Critical before expansion |
| Network layer | Multiple modules use `urllib` directly; broad exception handling is common | Inconsistent policies for timeout, retries, cancellation, auth, and test doubles | High |
| Platform imports | Windows COM modules are imported directly by shortcut resolution | Linux CI exercises only the portable subset; import boundaries remain brittle | High |
| Test shape | Approximately 216 pytest cases are concentrated in parsers, auth helpers, config, filters, events, and repository basics | Little confidence in scanning, persistence failure modes, MainWindow workflows, downloads, archives, or migrations | Critical |
| CI policy | Ruff lint and formatting steps use `continue-on-error` | The pipeline reports style failures without protecting the branch | High |
| Packaging | Packaging is a short manual PyInstaller recipe | No reproducible spec, artifact smoke test, signing, upgrade/uninstall, or release channel | High |
| Documentation | Several plans and session summaries overlap and contain stale status claims | No single source of truth for roadmap, decisions, or current architecture | Medium |

### 3.3 Key risks to address first

1. **Data loss or silent fallback divergence.** A failed primary save can write to a temporary fallback while later loads continue reading the primary file.
2. **Mutation outside a transaction.** UI code can mutate shared `Game` objects and collections directly, making undo, audit, validation, and tests unreliable.
3. **UI lifecycle fragility.** Mixin methods rely on attributes created elsewhere and on construction order.
4. **Background-operation inconsistency.** Scans, updates, icons, downloads, and extraction use different worker and cancellation patterns.
5. **Security ambiguity.** Credential and session storage must have an explicit Windows security model and threat assessment before broader authenticated automation.
6. **Feature duplication.** New acquisition work should stop until download/archive ownership is consolidated.

---

## 4. Design principles and non-negotiables

1. **No user-data loss.** Every migration is backed up, versioned, reversible where practical, and tested with fixtures.
2. **One authoritative state path.** Views request commands; application services validate and mutate; repositories persist; events describe completed changes.
3. **Local-first and explicit network behavior.** The app remains useful offline, and background network access is visible and configurable.
4. **Qt model/view before custom widget fleets.** Use `QAbstractListModel`/proxy models/delegates for large collections instead of one QWidget per item.
5. **Capabilities, not platform assumptions.** Windows-only adapters are isolated behind interfaces; portable logic remains testable on CI.
6. **Progressive disclosure.** Primary workflows stay obvious; advanced metadata and automation do not crowd normal browsing.
7. **Recoverable long-running work.** Jobs expose progress, cancellation, retry, logs, and resumable state where the underlying protocol permits it.
8. **Accessibility is a release requirement.** Keyboard navigation, focus visibility, readable scaling, reduced motion, semantic color, and screen-reader labels are designed in.
9. **No silent failure.** Errors are typed, actionable, logged with context, and shown at the appropriate level without leaking secrets.
10. **Measured performance.** Startup, filtering, scrolling, memory, scans, and save latency have budgets and regression tests.

---

## 5. Target architecture

### 5.1 Layered structure

```text
src/app/
├── domain/
│   ├── entities/          # Game, Collection, SavedView, Source, LaunchProfile
│   ├── value_objects/     # Version, GameId, paths, status, health result
│   ├── rules/             # Pure matching, comparison, collection predicates
│   └── events.py          # Typed immutable domain events
├── application/
│   ├── commands/          # AddGame, EditMetadata, LaunchGame, StartScan, ...
│   ├── queries/           # LibraryQuery, GameDetailsQuery, UpdateQuery
│   ├── services/          # Orchestration and transaction boundaries
│   ├── jobs/              # Durable job definitions and coordinator
│   └── dto/               # UI-safe read models
├── infrastructure/
│   ├── persistence/       # SQLite repositories, migrations, backup/import
│   ├── platform/windows/  # .lnk resolution, DPAPI, shell integration
│   ├── network/           # HTTP client, policies, source adapters
│   ├── acquisition/       # Host adapters, download/extract/install adapters
│   └── telemetry/         # Structured local diagnostics
├── presentation/
│   ├── shell/             # App shell and navigation
│   ├── library/           # Qt models, proxies, delegate, controller, view
│   ├── details/
│   ├── updates/
│   ├── health/
│   ├── downloads/
│   ├── settings/
│   └── shared/            # Design system and reusable controls
└── bootstrap.py           # Composition root / dependency wiring
```

The existing packages should migrate gradually into this shape. Do not move files solely to make the tree look complete; each move must establish a dependency boundary and have tests.

### 5.2 Dependency rule

```text
presentation → application → domain
infrastructure ────────────→ domain/application ports
bootstrap wires concrete infrastructure into application and presentation
```

- Domain code must not import PySide6, filesystem APIs, HTTP libraries, or storage implementations.
- Application services may depend on abstract ports, clocks, and job schedulers.
- Presentation receives read models and dispatches commands; it does not own persistence.
- Infrastructure is replaceable and tested through contracts.

### 5.3 Core domain decomposition

Replace the single expanding record with focused concepts:

| Concept | Responsibility |
|---|---|
| `Game` | Identity, title, user metadata, status, rating, tags, notes |
| `LaunchProfile` | Shortcut, executable, arguments, working directory, launch preference, last validation |
| `SourceReference` | Provider, canonical URL/external ID, installed/source version, last check, provider metadata |
| `Installation` | Install path, executable path, archive relationship, installed state |
| `PlayActivity` | Last played, launch count; later supports sessions/history |
| `Artwork` | Icon source, cache key, dominant color; presentation caches do not pollute the core entity |
| `Collection` | Manual membership or a validated query specification |
| `SavedView` | Named search/filter/sort/layout state |
| `Job` | Durable scan/check/download/extract/install operation and lifecycle |
| `HealthFinding` | Stable code, severity, affected resource, explanation, remediation state |

Use immutable value objects for IDs, versions, URLs, and normalized paths where they improve invariants. Do not over-engineer every string into a class.

### 5.4 Command/query flow

Example edit flow:

```text
DetailsView
  → UpdateGameMetadata command
  → LibraryApplicationService
  → validate + repository transaction
  → GameUpdated event
  → Library read model refreshes affected row
  → Details and status views update
```

Example scan flow:

```text
ScanView → StartScan command → JobCoordinator
  → ShortcutScanner port → discovered candidates
  → MergePolicy produces preview
  → user confirms destructive/ambiguous changes
  → repository transaction
  → ScanCompleted event + durable job result
```

### 5.5 Background job model

Use one coordinator for scans, source checks, downloads, extraction, installation, backups, and artwork refresh.

Every job must have:

- Stable ID and job type.
- `queued`, `running`, `paused` where meaningful, `succeeded`, `failed`, `cancelled` states.
- Structured progress (`completed`, `total`, message, optional throughput/ETA).
- Cancellation token checked by adapters.
- Typed result/error with redacted diagnostics.
- Persistence for jobs that need resume or post-crash history.
- Concurrency group and policy (for example, maximum downloads versus one library migration).

Qt worker objects should be presentation/infrastructure adapters around this model rather than separate orchestration systems.

---

## 6. Data and migration strategy

### 6.1 Storage decision

Adopt **SQLite as the primary metadata store**, while retaining JSON as a supported import/export and emergency-readable backup format.

Why SQLite:

- Atomic transactions and crash-safe journaling.
- Explicit schema versions and migrations.
- Efficient indexed filtering/sorting for large libraries.
- Separate tables for sources, launch profiles, jobs, findings, and history without rewriting the entire library.
- Easier uniqueness, foreign-key, and validation constraints.
- Built-in backup API and mature Python support.

Do not introduce an ORM initially. Use a small explicit data mapper and SQL migration files so behavior remains transparent and packaging stays simple.

### 6.2 Proposed schema groups

- `schema_migrations`
- `games`
- `game_tags` and `tags`
- `launch_profiles`
- `sources`
- `installations`
- `play_activity`
- `collections` and `collection_members`
- `saved_views`
- `jobs` and optional `job_events`
- `activity_log` — durable application-activity/audit records for the Activity view (launches, edits, imports, checks, failures, recoverable actions), independent of `jobs`/`job_events`
- `health_findings`
- `app_settings`
- `provider_cache` with expiry and provenance

### 6.3 Migration contract

1. On first revamp launch, detect the absence of the SQLite database.
2. Validate and parse the existing JSON without modifying it.
3. Create a timestamped backup of library, settings, auth/session metadata, and relevant job files.
4. Import into a new temporary database.
5. Run integrity checks: row counts, required identities, collection references, datetime/path normalization, and duplicate detection.
6. Atomically promote the temporary database.
7. Record import metadata and the original backup location.
8. While rollback to the pre-revamp release is still supported, keep the legacy JSON synchronized with post-migration edits so a downgrade cannot silently discard newer data. Do this with **compatibility dual-writing** (every committed change is written to both SQLite and a legacy-compatible `library.json`) or, at minimum, an **automatic legacy-JSON export on each save**. A manual “Export legacy-compatible JSON” action is offered in addition, but is not sufficient on its own to make rollback safe. Treat the legacy JSON as read-only only after the rollback window closes (no supported downgrade path remains).
9. If any step fails, leave the old app data untouched and show a recovery report.

### 6.4 Immediate safety improvements before SQLite

Milestone 1 should harden current JSON persistence so users are protected during the transition:

- Write to a sibling temporary file, flush, `fsync`, then atomically replace.
- Keep a rotating known-good backup.
- Validate serialized data before replacement.
- Surface the actual active fallback location and use it consistently for subsequent reads.
- Add explicit top-level schema versions and migration functions.
- Serialize every datetime field, including download timestamps, consistently.
- Remove dead APIs that intentionally raise `NotImplementedError` after call sites are verified.

---

## 7. UX and interaction redesign

### 7.1 Information architecture

Use six durable destinations:

1. **Library** — browse, search, filter, organize, and launch.
2. **Updates** — review source checks, compare versions, and start update workflows.
3. **Health** — diagnose missing or inconsistent resources and run repairs.
4. **Downloads** — see active and historical acquisition/install jobs.
5. **Activity** — recent imports, launches, edits, checks, failures, and recoverable actions, reconstructed after restart from the durable `activity_log` table (not only from in-memory job events).
6. **Settings** — library locations, appearance, network/providers, storage, shortcuts, diagnostics.

Collections and saved views belong within Library navigation rather than acting as separate top-level modes.

### 7.2 Shell

- **Left navigation rail:** durable destinations, then collapsible Collections and Saved Views.
- **Command bar:** page title, global search/command palette trigger, contextual primary action, overflow menu.
- **Content workspace:** page-specific toolbar and primary view.
- **Inspector:** optional right-side panel for selected game(s), preserving context rather than opening modal forms.
- **Activity center:** non-modal progress and error surface for background jobs.
- **Status strip:** selection count, result count, active filter summary, sync/offline state only when relevant.

At narrow widths, collapse the inspector first and then the navigation rail. Do not compress every control into one row.

### 7.3 Library experience

**Default browse view**

- Use a real Qt item model, `QSortFilterProxyModel`, `QListView` in icon mode, and `QStyledItemDelegate`.
- Keep grid and compact list presentations as delegates over the same model.
- Preserve selection by stable game ID across sorting/filtering.
- Render card information by priority: artwork, title, status/update/health indicators, then optional secondary metadata.
- Load artwork asynchronously by cache key; repaint only the affected index.

**Search and filters**

- One query box with immediate results and clear keyboard focus.
- Filter popover for status, rating, tags, source, install/health/update state, and collection.
- Active filters become removable chips.
- Saved Views capture query, filters, sort, grouping, density, and visible fields.
- Command palette exposes navigation and actions but does not replace discoverable controls.

**Selection and bulk work**

- Shift/Ctrl multi-select and Select All Results.
- Bulk action bar appears only when selection exists.
- Every destructive bulk action previews impact and supports undo when feasible.
- Drag-and-drop remains a convenience, never the only path to collection membership.

### 7.4 Game inspector

Organize information into concise sections:

- **Overview:** artwork, title, status, rating, tags, play action, health/update badges.
- **Launch:** selected profile, target, arguments, working directory, test/repair action.
- **Source & version:** provider, URL, installed/source versions, last check, check now.
- **Files:** install, archive, saves, backups, reveal actions.
- **Notes & activity:** notes and recent game-specific history.

Use explicit Edit/Save/Cancel state or reliable per-field commits through commands. Avoid the current ambiguous model where widgets can mutate shared entities directly.

### 7.5 Updates workflow

1. Check selected sources or all due sources.
2. Show durable results grouped into Update available, Current, Unknown, Failed, and Local newer.
3. Explain the comparison using raw and parsed versions.
4. Let the user inspect source changes and available downloads before acting.
5. Start a single update job that captures download → verify → extract → install/replace → update metadata.
6. Never overwrite an installation without a preview, backup policy, and rollback story.

### 7.6 Health workflow

- Findings have stable codes and severities, not ad-hoc strings.
- Group by actionability: Needs attention, Suggested, Ignored, Resolved.
- Each finding answers: what failed, evidence, impact, and next safe action.
- Repairs produce commands/jobs and a result; they do not mutate files from inside a widget.
- “Ignore” includes scope and optional expiry so stale ignores can be revisited.

### 7.7 First-run and empty states

First run should ask only for:

1. Shortcut/library folder.
2. Whether to scan now.
3. Optional update-provider setup after the first useful library appears.

Empty states should teach one next action. Advanced F95 authentication, archive passwords, custom themes, and download tuning belong in Settings or contextual onboarding later.

### 7.8 Design system

Create a small tokenized system instead of expanding a single theme module:

- `ColorTokens`, `TypographyTokens`, `SpacingTokens`, `RadiusTokens`, `MotionTokens`.
- Semantic roles: canvas, surface, raised, text, muted, accent, focus, success, warning, danger, update, health severities.
- Reusable components: command button, icon button, segmented control, filter chip, empty state, section header, form row, job row, badge, inline message.
- SVG icon assets through `QIcon`; emoji must not be the primary icon system because rendering varies by platform/font.
- Ship Dark, Light, and High Contrast first. Treat experimental visual themes as optional follow-up until component coverage is complete.

### 7.9 Accessibility acceptance criteria

- Every action is reachable and operable by keyboard.
- Focus order follows visual order; focus is always visible.
- Icon-only actions have accessible names and tooltips.
- Text remains usable at 100%, 125%, 150%, and 200% scale.
- Status is never encoded by color alone.
- Reduced-motion setting disables nonessential animation.
- Minimum contrast is verified for standard and high-contrast themes.
- Screen-reader smoke tests cover navigation, library items, inspector fields, dialogs, and job status.

---

## 8. Service consolidation

### 8.1 Scanning and launch

Define ports:

```python
class ShortcutScanner(Protocol):
    def scan(self, root: Path, cancellation: CancellationToken) -> ScanSnapshot: ...

class ShortcutResolver(Protocol):
    def resolve(self, path: Path) -> LaunchCandidate: ...

class GameLauncher(Protocol):
    def launch(self, profile: LaunchProfile) -> LaunchResult: ...
```

- Move COM/shell code into `infrastructure/platform/windows`.
- Produce a scan preview that distinguishes add, update, unchanged, duplicate, missing, and ambiguous.
- Make merge rules pure and fixture-tested.
- Record launch failure reason and attempted profile without swallowing it into a generic UI message.

### 8.2 HTTP and source providers

Create one injected HTTP client with:

- Default headers and explicit timeouts.
- Retry policy only for safe/retriable failures.
- Cancellation.
- Cookie/session integration.
- Bounded cache with provenance and expiry.
- Redacted request diagnostics.
- Fake transport for deterministic tests.

Provider interface:

Every network-bound provider operation receives a `RequestContext` carrying the
cancellation token (plus correlation id, deadline, and diagnostic level) so a
provider blocked in an HTTP request can observe cancellation cooperatively and
shut down cleanly — matching the cancellable-job and HTTP-client requirements.
The context is threaded through to the injected HTTP client, which honors the
same token, so cancellation propagates end to end rather than stopping at the
job boundary.

```python
class SourceProvider(Protocol):
    provider_id: str
    def canonicalize(self, reference: str) -> SourceIdentity: ...
    def fetch_metadata(self, identity: SourceIdentity, ctx: RequestContext) -> SourceSnapshot: ...
    def list_artifacts(self, snapshot: SourceSnapshot, ctx: RequestContext) -> list[Artifact]: ...
```

`RequestContext` exposes at least `cancel_token: CancellationToken`, `deadline`,
`correlation_id`, and `diagnostics_level`; long-running provider work must poll
`ctx.cancel_token` (or pass it to the HTTP client) and raise `OperationCancelled`
promptly when cancellation is requested.

F95 becomes one provider implementation, not a set of assumptions spread through general-purpose UI and services.

### 8.3 Authentication and secrets

- Document the threat model: local account attacker, copied app-data folder, logs, crash reports, and network interception.
- Use Windows DPAPI/Credential Manager through a `SecretStore` port for remembered secrets.
- Do not derive a reusable encryption key from predictable local values as the long-term design.
- Separate credentials from session cookies and let users clear either.
- Redact tokens, cookies, usernames where appropriate, download URLs with secrets, and filesystem paths according to diagnostic level.
- Add an explicit consent and status surface for authenticated provider access.

### 8.4 Download, extraction, and installation

Consolidate current overlapping services into:

- `AcquisitionPlanner`: selects compatible artifacts and mirrors.
- `HostAdapter`: resolves an artifact into a downloadable stream/capabilities.
- `DownloadExecutor`: writes `.part`, supports range resume when available, verifies expected size/hash.
- `ArchiveInspector`: detects format, parts, password needs, and unsafe paths.
- `ExtractionExecutor`: extracts into staging and blocks path traversal.
- `InstallPlanner`: computes file operations and backup requirements.
- `InstallExecutor`: applies staged operations transactionally where practical and supports rollback.

Security gates:

- Never extract directly over an existing install.
- Reject archive entries escaping the staging root.
- Warn on executable/script content based on policy; never auto-run downloaded binaries.
- Verify free disk space before download/extract/install.
- Preserve provenance: source, artifact URL, host, version, timestamps, size/hash, and resulting install.

---

## 9. Quality strategy

### 9.1 Test pyramid

| Layer | Required coverage |
|---|---|
| Domain unit tests | Invariants, version comparison, merge policy, saved-view queries, collection rules, health rules |
| Repository contract tests | CRUD, transactions, constraints, concurrent access policy, migration compatibility |
| Migration fixtures | Every historical library/settings shape kept in `tests/fixtures/migrations` |
| Service tests | Scan, source checks, jobs, cancellation, retry, download resume, safe extraction, rollback |
| Qt model tests | Roles, row updates, selection identity, sort/filter behavior, async artwork repaint |
| UI workflow tests | First run, scan preview, edit, launch failure, saved view, bulk edit, health repair, update job |
| Packaging smoke tests | Start packaged app, resolve resources, create/open a disposable library, clean shutdown |

### 9.2 CI gates

Make all required checks blocking:

- Ruff lint and format.
- Static typing for domain/application code (Pyright or mypy; choose one after a short trial).
- Pytest with separate portable and Windows integration markers.
- Coverage thresholds by package, not one misleading global number.
- Dependency vulnerability/license audit.
- Migration fixture tests.
- Windows packaged smoke test on release candidates.

Suggested initial thresholds:

- Domain/application: 90% line coverage and branch coverage enabled.
- Infrastructure: 75% with contract/integration emphasis.
- Presentation: workflow coverage rather than a high line target.
- No decrease in total covered lines without an explicit PR note.

### 9.3 Performance budgets

Measure with fixed synthetic libraries of 100, 1,000, and 10,000 games.

| Operation | Target |
|---|---|
| Warm app shell visible, 1,000 games | < 1.5 s on reference hardware |
| Interactive library, 1,000 games | < 2.0 s |
| Search/filter update, 10,000 games | p95 < 100 ms |
| Sort change, 10,000 games | p95 < 150 ms |
| Scroll | 60 FPS target; p95 frame < 25 ms |
| Single metadata commit | p95 < 50 ms excluding explicit network/file jobs |
| Memory after browsing 10,000 games | < 350 MB target, measured and trended |
| Clean shutdown after cancelling jobs | < 3 s |

Targets must be validated on agreed reference hardware and adjusted once, during Milestone 0, if measurement proves them unrealistic.

### 9.4 Observability

- Structured local logs with operation/job IDs and event names.
- In-app diagnostics export that redacts secrets and can optionally redact paths/titles.
- Startup timing, model load timing, query timing, worker queue depth, and failure categories.
- Rotating logs and bounded caches/history.
- No third-party telemetry by default. Any future telemetry is opt-in and documented.

---

## 10. Delivery roadmap

### Milestone 0 — Baseline and scope lock (1 week)

**Goal:** Create a trustworthy baseline before structural edits.

**Deliverables**

- Archive stale planning documents or label them superseded by this plan.
- Record supported Windows/Python/PySide versions and representative library sizes.
- Add startup, filter, scroll, memory, scan, and save benchmarks.
- Create a feature inventory and trace each feature to an owner/module/test status.
- Add representative anonymized JSON migration fixtures.
- Decide whether F95 authenticated downloads are a release-blocking capability or an experimental feature flag.

**Exit criteria**

- Baseline report is reproducible.
- Critical workflows have a manual smoke checklist.
- Product scope and performance reference hardware are approved.

### Milestone 1 — Data safety and engineering gates (2 weeks)

**Goal:** Make the existing release safer while laying migration foundations.

**Deliverables**

- ✅ Atomic JSON writes, known-good backups, active-fallback markers, consistent fallback reads, and full datetime handling.
- 🟡 Explicit JSON schema migration registry is implemented for library v1 → v2; historical fixtures and corruption recovery UX remain.
- Blocking Ruff checks; introduce type checking for new core packages.
- Windows CI lane for platform integration tests.
- 🟡 Dead persistence APIs have been removed; repository mutation contracts still need clarification.
- Security review of credential/session storage and log redaction.

**Exit criteria**

- Fault-injection tests prove interrupted saves preserve a valid prior library.
- Every historical fixture loads and round-trips.
- Required CI checks are blocking and green.

### Milestone 2 — Domain and SQLite foundation (3 weeks)

**Goal:** Establish the long-term data and business boundary.

**Deliverables**

- Domain entities/value objects and typed domain events.
- SQLite schema, migration runner, data mappers, repository contracts, backup/restore.
- One-time JSON importer with dry-run and integrity report.
- Application commands/queries for core library CRUD, collections, saved views, and launch recording.
- Composition root with dependency injection.

**Exit criteria**

- Existing fixtures migrate without loss.
- Core CRUD and queries run without PySide6 imports.
- The old UI can operate through a compatibility facade backed by SQLite.

### Milestone 3 — Unified jobs and platform/network adapters (2–3 weeks)

**Goal:** Standardize long-running and external work before replacing its UI.

**Deliverables**

- Job coordinator, cancellation, progress, durable history, and error model.
- Windows shortcut scanner/resolver/launcher adapters.
- Shared HTTP client and F95 provider adapter.
- Scan and update-check commands that publish typed results.
- Activity read model.

**Exit criteria**

- Scan and update checks have deterministic service tests.
- Cancellation and shutdown are tested.
- UI worker classes contain no business orchestration.

### Milestone 4 — New shell and library model/view (3 weeks)

**Goal:** Ship the performance and maintainability center of the revamp.

**Deliverables**

- New app shell, navigation, command bar, inspector host, activity center.
- `LibraryListModel`, proxy/filter model, grid/list delegates, stable selection.
- Saved Views and complete keyboard/multi-select behavior.
- Async artwork cache keyed independently of domain entities.
- Dark, Light, and High Contrast tokenized themes.

**Exit criteria**

- 10,000-item performance budgets pass.
- Core browse/edit/launch workflows pass UI automation.
- No QWidget-per-game architecture remains in the primary library view.

### Milestone 5 — Inspector, updates, and health workflows (2–3 weeks)

**Goal:** Replace the remaining daily workflows with command-driven experiences.

**Deliverables**

- Sectioned game inspector with validation and conflict-safe edits.
- Updates dashboard with explainable version state and provider failures.
- Health findings model, remediation commands, ignore/resolve history.
- Bulk edit preview and undo for supported metadata actions.
- First-run onboarding and contextual empty states.

**Exit criteria**

- Existing daily capabilities have parity or an approved deprecation.
- Accessibility checklist passes for shell, library, inspector, updates, and health.
- Old MainWindow mixins for migrated behavior are removed, not left as alternate paths.

### Milestone 6 — Acquisition pipeline (3–4 weeks, feature-flagged)

**Goal:** Replace overlapping download/archive code with a safe end-to-end pipeline.

**Deliverables**

- Acquisition planner, host adapters, resumable executor, verification.
- Safe archive inspection/extraction into staging.
- Install preview, backup policy, transactional apply/rollback.
- Downloads page and per-game update action.
- Provider authentication through OS-backed secret storage.

**Exit criteria**

- Supported host matrix has contract tests and documented limitations.
- Archive traversal, cancellation, disk-full, network failure, and rollback tests pass.
- Experimental flag is removed only when the full path meets quality/security gates.

### Milestone 7 — Release hardening and migration (2 weeks)

**Goal:** Produce a supportable Windows release.

**Deliverables**

- Reproducible PyInstaller spec and clean-machine packaged smoke tests.
- Installer strategy, upgrade/uninstall behavior, file associations if needed, and code-signing workflow.
- In-app backup/restore, diagnostics export, migration recovery, and release notes.
- Remove compatibility facades, dead services, stale themes, and superseded docs.
- Beta migration with anonymized copies and rollback rehearsal.

**Exit criteria**

- Zero open P0/P1 defects.
- No known data-loss defects.
- Migration success target ≥ 99.5% across fixture/beta runs.
- Crash-free manual beta sessions ≥ 99%.
- Release checklist and rollback package are complete.

---

## 11. Workstreams and ownership

Run milestones sequentially at the boundary level, but use parallel workstreams within each milestone:

| Workstream | Owns | Must not own |
|---|---|---|
| Product/UX | User flows, IA, component specs, usability/accessibility validation | Persistence or service implementation |
| Domain/application | Entities, commands, queries, policies, job semantics | Qt widgets or platform APIs |
| Data/infrastructure | SQLite, migrations, backup, Windows adapters, HTTP, secrets | UI state |
| Presentation | Qt models, delegates, controllers, views, design system | Direct filesystem/network/database calls |
| Quality/release | Fixtures, automation, benchmarks, CI, packaging, release checklist | Feature-specific hidden alternate implementations |

For a small team, these are responsibility hats rather than required separate people. Pull requests should still state which boundary they modify.

---

## 12. Dependency order and critical path

```text
Baseline
  ↓
Data safety + CI gates
  ↓
Domain contracts + SQLite/import
  ↓
Application commands/queries + unified jobs
  ↓
New shell + library model/view
  ↓
Inspector/updates/health
  ↓
Acquisition pipeline
  ↓
Packaging, beta migration, release
```

The visual redesign must not get ahead of the command/query and read-model contracts. The acquisition rewrite may begin in parallel after unified jobs and HTTP/provider boundaries exist, but it remains feature-flagged until the redesigned Downloads surface and security gates are complete.

---

## 13. Definition of done

A feature is complete only when:

- Product behavior and failure states are specified.
- Domain/application behavior has automated tests.
- Persistence migrations and backward compatibility are covered where applicable.
- UI supports keyboard, focus, scaling, and accessible naming.
- Background work supports cancellation and clean shutdown where applicable.
- Errors are typed, actionable, logged, and redacted.
- Performance impact is measured for hot paths.
- User-facing documentation and migration/release notes are updated.
- Superseded code is removed in the same milestone or tracked with a dated removal issue.
- CI is green with no required check marked informational.

---

## 14. Explicit deprecations and decisions

### Deprecate

- Direct mutation of repository-owned lists/entities from widgets or mixins.
- Full-library writes for ordinary metadata changes.
- Emoji as the primary icon system.
- Multiple independent download orchestrators.
- New behavior added to the `MainWindow` mixin graph.
- Informational-only lint checks.
- Session-summary documents as roadmap authority.

### Retain temporarily behind compatibility facades

- Existing JSON library as an import/export format.
- Existing UI while each destination reaches parity.
- Existing pure parsing/matching functions until moved behind provider/domain boundaries.
- Existing experimental themes, only if they require no special-case component code.

### Rejected alternatives

| Alternative | Reason rejected |
|---|---|
| Greenfield repository rewrite | High risk of feature loss, migration errors, and a long period with no shippable improvements |
| UI-only facelift first | Would cement new screens onto the same mutable state and persistence problems |
| Keep JSON permanently as primary store | Poor fit for transactions, histories, jobs, relationships, indexed queries, and safe incremental writes |
| Adopt Qt Quick/QML during this revamp | Adds framework migration risk without solving domain/data problems; PySide widgets can meet requirements with model/view/delegates |
| Build a plugin system now | Expands security and compatibility surface before core provider/job contracts stabilize |
| Add cloud sync now | Requires conflict resolution, identity, security, and service operations before local data semantics are stable |

---

## 15. First implementation slice

The first implementation PR after this plan should be deliberately narrow:

1. Add persistence fault-injection tests for current JSON save/load.
2. Implement atomic writes and rotating backup for library/settings.
3. Add complete datetime serialization for current `Game` fields.
4. Make fallback storage location explicit and consistently readable.
5. Turn Ruff lint/format into blocking CI checks after fixing the existing baseline or introducing a committed baseline configuration.
6. Add a Windows CI smoke lane that imports the app and exercises shortcut adapter boundaries with fakes/fixtures.

This slice materially reduces user risk, creates test seams, and does not require waiting for the SQLite or UI redesign.

---

## 16. Success measures

### User outcomes

- First useful library appears within five minutes for a new user.
- A returning user can find and launch a game in under ten seconds.
- Update and health results explain both state and next action.
- Destructive operations always preview impact and provide recovery guidance.
- Existing libraries migrate without manual repair in at least 99.5% of tested cases.

### Engineering outcomes

- Presentation has no direct persistence/network/platform calls.
- New core code has typed boundaries and package-level quality gates.
- Primary library view meets the 10,000-item performance budget.
- No source file exceeds 500 lines without a documented exception and review.
- One job framework, one HTTP policy layer, one acquisition pipeline, and one active metadata store.
- Release artifacts are reproducible and smoke-tested on clean Windows environments.

---

## 17. Immediate issue backlog

Create tracking issues in this order:

1. `REVAMP-001` Baseline benchmark harness and reference datasets.
2. `REVAMP-002` Atomic JSON persistence and recovery.
3. `REVAMP-003` Historical migration fixture corpus.
4. `REVAMP-004` Blocking lint/format and type-check baseline.
5. `REVAMP-005` Windows adapter isolation and CI lane.
6. `REVAMP-006` Domain model and repository contracts.
7. `REVAMP-007` SQLite schema/migration/importer.
8. `REVAMP-008` Command/query application layer.
9. `REVAMP-009` Unified job coordinator.
10. `REVAMP-010` Shared HTTP client and provider contract.
11. `REVAMP-011` New shell and navigation.
12. `REVAMP-012` Qt library model/proxy/delegates.
13. `REVAMP-013` Saved Views and query persistence.
14. `REVAMP-014` Inspector rewrite.
15. `REVAMP-015` Updates workflow rewrite.
16. `REVAMP-016` Health findings and remediation model.
17. `REVAMP-017` Acquisition/download/archive consolidation.
18. `REVAMP-018` OS-backed secrets and provider security review.
19. `REVAMP-019` Packaging, installer, and clean-machine smoke tests.
20. `REVAMP-020` Beta migration and rollback rehearsal.

---

## 18. Plan governance

- This document is the authoritative revamp roadmap until replaced by an approved architecture decision or release plan.
- Architectural decisions that alter a dependency boundary, storage choice, security model, or supported platform require a short ADR in `docs/adr/`.
- Update milestone status here monthly; do not duplicate status into new session-summary files.
- Each milestone ends with a demo, benchmark comparison, migration/recovery check, and a go/no-go review for the next milestone.
- If schedule pressure arises, cut optional features or keep them behind flags. Do not cut data safety, migration, accessibility, cancellation, or required CI gates.
