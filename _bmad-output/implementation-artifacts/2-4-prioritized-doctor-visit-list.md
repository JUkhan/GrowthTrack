---
baseline_commit: 87f02fe
---

# Story 2.4: Prioritized Doctor Visit List

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want a doctor visit list computed per territory and ranked by Target Priority,
so that each Sales Rep's Daily Report reflects accurate, prioritized visit guidance.

## Acceptance Criteria

1. **Given** current doctor/territory data, **when** the visit list is computed for a territory, **then** each entry includes Doctor Name, Territory, and Target Priority, ranked by priority. [Source: epics.md#Story 2.4, prd.md#FR-5, ARCHITECTURE-SPINE.md#CAP-7]
2. **Given** a doctor record, **when** stored or displayed, **then** it contains no patient health data — only name, territory, and priority. [Source: epics.md#Story 2.4, prd.md#FR-5, prd.md#NFR-5]
3. **Given** the doctor list is computed, **when** consumed downstream, **then** it feeds Epic 4's Daily Report generation and is not rendered as its own Dashboard/portal screen (Daily-Report-only). [Source: epics.md#Story 2.4, EXPERIENCE.md#Information Architecture]
4. **Given** this story ships before Epic 4 exists, **when** its correctness is verified, **then** verification happens via automated tests against the domain computation and repository layer directly (ranking output for a known fixture territory/dataset) — this story's acceptance does not wait on Epic 4's Daily Report to visually confirm the list, since no portal screen will ever exist to check it against. [Source: epics.md#Story 2.4]

## Tasks / Subtasks

- [x] Task 1: Extend the `Doctor` read-side port + adapter (AC: #1, #2)
  - [x] `ports/doctors.py` — add one abstract method alongside the existing `upsert_many`, matching `ports/brand_performance.py`'s exact `list_all` shape (Story 2.3 precedent — same current-snapshot-only entity, same read pattern):
    ```python
    @abstractmethod
    async def list_all(self) -> list[Any]:
        """All current Doctor rows (current-snapshot table, not a time
        series — same shape as BrandPerformance). Ordered by territory
        ascending, then priority ascending. Empty list when the table
        has never been populated, never None."""
        ...
    ```
    `Any`-typed, matching this port's existing `upsert_many` style (`ports/` can't import `domain.models` — import-linter contract).
  - [x] `adapters/persistence/doctors.py` — implement `list_all` on `SqlAlchemyDoctorRepository`: `SELECT * FROM doctors ORDER BY territory ASC, priority ASC`, mapped to `domain.models.Doctor` via a **module-level `_to_domain` free function** — not a `@staticmethod` on the repository class. Story 2.3's Review Findings explicitly flagged `SqlAlchemyBrandPerformanceRepository`'s `_to_domain` being a `@staticmethod` instead of the intended module-level free function as a (non-blocking) literal-fidelity deviation; this story should implement it as a free function correctly the first time rather than repeat that finding.
  - [x] No Alembic migration needed — `doctors` already exists (Story 2.1, `adapters/persistence/doctors.py`); this task only adds a read method over an existing table. If you find yourself writing a migration for this story, you've misread this task.

- [x] Task 2: `domain/metrics.py` — doctor visit list ranking computation (AC: #1, #2, #4)
  - [x] Add to the existing module (co-located with `DashboardMetricsService`/`BrandPerformanceService` — the Architecture spine's Capability map fixes CAP-7 "Doctor visit list" as living in `domain/metrics`, same file as CAP-2/CAP-6):
    ```python
    @dataclass
    class DoctorEntry:
        doctor_name: str
        territory: str
        target_priority: int

    class DoctorVisitListService:
        def __init__(self, doctors: DoctorRepository) -> None: ...

        async def get_visit_list(self, territory: str) -> list[DoctorEntry]: ...
    ```
    Constructed with the port only (never a concrete adapter — AD-1). A **separate class** from `DashboardMetricsService`/`BrandPerformanceService`, not a method added to either — CAP-7 is its own capability row in the Capability map, "consumed by CAP-3/4 only" (Epic 4's not-yet-built Daily Report generation, via `domain/notifications`), with zero dependency on the Dashboard API or either existing service.
  - [x] **`_rank_doctors_for_territory` — this story's own ranking-direction design call, isolate it as its own small pure function, exactly like Stories 2.2/2.3's `_aggregate_company_wide`/`_classify_brands` isolated-default pattern:**
    ```python
    def _rank_doctors_for_territory(rows: list[Doctor], territory: str) -> list[DoctorEntry]:
        """[ASSUMPTION — ranking direction, not flagged as a blocking business
        decision in epics.md Story 2.4 (unlike Story 2.3 AC #4's thresholds or
        Story 2.2 AC #6's formula, which explicitly withhold `done` pending
        stakeholder sign-off) — but genuinely undefined by any planning doc.
        Neither prd.md's Glossary ("Target Priority — the ranking used to
        order the Doctor visit list") nor entities.md's field list say
        whether a LOWER Doctor.priority number means "visit first" or
        "visit last". This function treats lower priority = higher
        urgency = visit first (ascending sort), mirroring this exact
        codebase's already-established `BrandPerformance.rank` convention
        (Story 2.3: "ascending rank = better") for the same kind of
        Source-System-ingested ordinal field. If a business stakeholder
        later confirms the opposite direction, this is a one-function,
        one-line change (flip to descending) — nothing else in this
        story's design depends on the direction chosen.
        """
        matching = [r for r in rows if r.territory == territory]
        ranked = sorted(matching, key=lambda r: (r.priority, r.name))
        return [
            DoctorEntry(doctor_name=r.name, territory=r.territory, target_priority=r.priority)
            for r in ranked
        ]
    ```
  - [x] `get_visit_list()` body: `rows = await self._doctors.list_all()`; `return _rank_doctors_for_territory(rows, territory)`.
  - [x] Do **not** touch `DashboardMetricsService`, `BrandPerformanceService`, `_aggregate_company_wide`, or `_classify_brands` — this task is purely additive to `domain/metrics.py`.
  - [x] Do **not** build any API route or frontend component for this story — see Task 3.

- [x] Task 3: No API route, no frontend — explicit non-scope (AC: #3)
  - [x] Unlike Story 2.3 (which added `GET /dashboard/brand-performance` + a frontend section), this story adds **no `api/` route and no `web/` component**. epics.md's own AC #3/#4 state the doctor visit list is Daily-Report-only, feeding Epic 4 (not yet built) directly via `DoctorVisitListService`, and EXPERIENCE.md's Information Architecture section explicitly says: *"Doctor Visit Prioritization (FR-5) has no dedicated portal screen ... The table below deliberately does not invent a Doctors screen beyond what the FRs support."*
  - [x] **`EXPERIENCE.md` line 28 also mentions `GET /doctors` "backs report generation"** — this is a stale/superseded reference to an earlier draft of `architecture-diagrams.md` (no such route or diagram entry exists in the current planning docs; `ARCHITECTURE-SPINE.md`'s Capability map fixes CAP-7 as `domain/metrics` only, with no `api/` path listed, unlike every other CAP row). Treat `ARCHITECTURE-SPINE.md` + epics.md's explicit AC #3/#4 as authoritative over that one EXPERIENCE.md phrase — do **not** build a `GET /doctors` endpoint for this story. When Epic 4's Daily Report generation is eventually built, it will call `DoctorVisitListService.get_visit_list(territory)` directly from `domain/notifications` (same in-process pattern `BrandPerformanceService` is designed for), not through an HTTP round-trip.

- [x] Task 4: Tests (AC: #1, #2, #4)
  - [x] `tests/domain/test_doctor_visit_list_service.py` — new file, hand-written `FakeDoctorRepository` (no mocking library, per this repo's established convention from `test_brand_performance_service.py`/`test_dashboard_metrics_service.py`). Cases:
    - A known fixture territory with several doctors of differing `priority` → returned in ascending-priority order (lowest number first = visit first), each entry carrying `doctor_name`/`territory`/`target_priority`.
    - Doctors from other territories are excluded from a given territory's result.
    - A territory with zero matching doctors (but the repository has rows for other territories) → empty list, no exception.
    - Empty repository (`list_all()` returns `[]`) → empty list for any territory queried.
    - Two doctors in the same territory sharing the same `priority` → both included, tie broken by `doctor_name`, deterministic across repeated calls (mirrors `test_classify_brands_top_ties_broken_by_brand_name_and_both_retained`'s pattern).
    - `DoctorVisitListService.get_visit_list()` delegates to `_rank_doctors_for_territory` correctly (service-level integration case, mirroring `test_brand_performance_service_get_summary_delegates_to_classify_brands`).
  - [x] `tests/adapters/persistence/test_doctor_repository.py` — extend with a `list_all` case: multiple seeded rows across two territories returned ordered by territory ascending then priority ascending; empty table returns `[]`, not `None` (mirrors `test_brand_performance_repository.py`'s `test_list_all_returns_empty_list_when_table_is_empty`/`test_list_all_returns_rows_ordered_by_rank_ascending`).
  - [x] `tests/domain/test_ingestion_service.py:98-103` — its existing `FakeDoctorRepository` (used by `SourceSystemImportService`'s tests) needs one new stub method once `DoctorRepository` gains the abstract `list_all` method, or it stops being instantiable:
    ```python
    async def list_all(self) -> list:
        raise NotImplementedError
    ```
    Same fix Story 2.3 already applied to `FakeBrandPerformanceRepository` in this same file for the identical reason — not a scope change to Story 2.1's ingestion tests, just keeping an existing test double instantiable against its port's new abstract method.
  - [x] `tests/conftest.py` — no change needed; `_clean_tables` already covers `doctors` (added in Story 2.1).
  - [x] `uv run lint-imports` after this story's changes — confirm `ports/doctors.py` stays `domain`-free and `domain/metrics.py`'s new code only imports from `ports/`.

## Dev Notes

- **This story's scope is deliberately narrow: domain computation + repository read, nothing else.** No config thresholds (unlike Story 2.3's `brand_top_n`/etc. — there's no count/classification question here, only an ordering direction), no Alembic migration, no API route, no frontend component. If your task list for this story grows beyond Tasks 1-4 above, re-read epics.md's AC #3/#4 — you've likely scope-crept into Epic 4 territory.
- **`Doctor` already exists exactly as needed.** Story 2.1 created `domain/models.py`'s `Doctor` dataclass (`id`, `external_doctor_id`, `name`, `territory`, `priority` — no patient health data, matching AC #2/NFR-5 already), the `doctors` table, and `DoctorRepository.upsert_many`. This story adds a **read** method only (`list_all`), the exact shape Story 2.3 already established for the sibling current-snapshot entity `BrandPerformance`. Do not redefine `Doctor`, do not add new fields, do not re-create the table.
- **Ranking direction is this story's one genuinely open design call** (see `_rank_doctors_for_territory`'s docstring in Task 2) — lower `priority` number = visit first, by analogy with `BrandPerformance.rank`'s already-established ascending-is-better convention in this exact codebase. Unlike Stories 2.2's AC #6 (Achievement %/Growth % formula) or 2.3's AC #4 (brand thresholds), epics.md's Story 2.4 ACs do **not** flag this as a blocking pre-implementation business sign-off — so this story **may** be marked `done` on this assumption, but the reasoning is still isolated in its own pure function so a future direction-flip is a one-line change, not a refactor.
- **No API route or frontend, and EXPERIENCE.md's `GET /doctors` mention is stale — see Task 3.** This is a deliberate deviation from Story 2.3's shape (which did add a Dashboard API route + component for the sibling `BrandPerformance` capability) — Brand Performance is an *additional Dashboard section* per its own AC #3, while the Doctor visit list is explicitly *not* a Dashboard/portal surface per this story's AC #3 and EXPERIENCE.md's Information Architecture note. Don't pattern-match Story 2.3's Task 3/4/6 (API route + Vite proxy + frontend component) onto this story.
- **Verification posture**: per AC #4 and Story 2.1's own Dev Notes (which anticipated this exact situation — "the same posture epics.md explicitly calls out for Story 2.4"), this story's correctness is proven entirely by Task 4's domain-service and repository-level tests against a known fixture territory/dataset. There is no portal screen to visually confirm against, now or ever — over-test rather than under-test this story's ranking logic.
- **`_rank_doctors_for_territory` takes the full `list_all()` result and filters in Python**, rather than adding a `list_by_territory(territory)` port method with its own SQL `WHERE` clause. This mirrors `BrandPerformanceService.get_summary()`'s exact shape (fetch everything via one `list_all()` call, do all business logic — filtering, ranking — in the domain layer) rather than pushing filtering into the port. Phase 1 scale (a single organization's doctor roster) makes this the simpler, sufficient choice; if Epic 4 later needs to compute visit lists for many territories in one Daily Report generation run, a single `list_all()` call plus in-memory grouping is also more efficient than N per-territory queries.

### Project Structure Notes

- Modified backend files only: `ports/doctors.py` (new `list_all` method), `adapters/persistence/doctors.py` (implementation), `domain/metrics.py` (new `DoctorEntry`/`DoctorVisitListService`/`_rank_doctors_for_territory`, additive to Stories 2.2/2.3's existing content), `tests/domain/test_ingestion_service.py` (one new stub method on the existing `FakeDoctorRepository`).
- New backend test file: `tests/domain/test_doctor_visit_list_service.py`. Modified: `tests/adapters/persistence/test_doctor_repository.py`.
- No frontend files, no `api/` changes, no Alembic migration, no `config.py` changes, no `docker/` changes.

### Previous Story Intelligence (from 2-3-brand-performance-analytics)

- `domain/metrics.py` already exists with `DashboardMetricsService`/`BrandPerformanceService` — this story adds a third service to the same file, matching the Architecture spine's Capability map (`domain/metrics` owns CAP-2, CAP-6, and now CAP-7).
- The isolated-pure-function-with-a-docstring pattern for a flagged assumption (`_aggregate_company_wide`, then `_classify_brands`) is reused a third time here for `_rank_doctors_for_territory` — same shape, though this story's assumption (ranking direction) is not itself a blocking `done`-gate the way the prior two were, since epics.md doesn't flag it as one.
- Story 2.3's Review Findings flagged `_to_domain` being implemented as a `@staticmethod` instead of the intended module-level free function (non-blocking, but noted for literal fidelity) — this story's `adapters/persistence/doctors.py#list_all` should implement `_to_domain` as a free function from the start (Task 1).
- Story 2.3's Review Findings also flagged that `FakeBrandPerformanceRepository` in `tests/domain/test_ingestion_service.py` needed a new stub method when its port gained an abstract `list_all` — this story's `DoctorRepository` gaining the same method means `FakeDoctorRepository` in that same file needs the identical treatment (Task 4).
- `BrandPerformanceService`'s constructor takes only the port (plus config thresholds, which this story's `DoctorVisitListService` doesn't need) — same "port-only construction, never a concrete adapter" precedent (AD-1) this story's service follows.

### Git Intelligence

- `HEAD` is `87f02fe` ("code review"), working tree clean; prior substantive commits are `7aad716` ("story 2.2") and `b8fb965` ("Story 2.1: nightly sales & reference data ingestion").
- Migration chain is unchanged by this story (still ends at Story 2.1's `e054c35b938f` revision, unaffected by Stories 2.2/2.3 too) — confirms Task 1's "no new Alembic migration" call.
- Commit style: one commit per logical unit of work, imperative summary line, ending with the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4: Prioritized Doctor Visit List] (all 4 ACs, verbatim basis for this story's AC list, including the explicit "no portal screen ever" language)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1: Nightly Sales & Reference Data Ingestion] (Dev Notes anticipating this story's verification-without-a-screen posture: "the same posture epics.md explicitly calls out for Story 2.4")
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#FR-5] ("System surfaces a doctor visit list per territory, ranked by Target Priority... Each entry includes Doctor Name, Territory, and Target Priority... No patient health data is included or implied")
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#Glossary "Doctor"/"Target Priority"/"Territory"] (field definitions; "Target Priority — The ranking used to order the Doctor visit list within a Territory" — direction unspecified, basis for this story's flagged assumption)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#§4.5] ("Brand and doctor entries in the report are condensed to names only... the full field set... Territory, Target Priority for doctors — remains available on the Dashboard" — NOTE: this line describes the general condensed-report-vs-full-detail pattern; per epics.md's explicit AC #3/#4, the doctor list's "full field set" destination is Epic 4's Daily Report generation code path, not an actual Dashboard screen, since none exists for doctors)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#NFR-5] (no patient health data collected/stored — Doctor limited to name, territory, priority)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Capability → Architecture Map] (CAP-7: "Doctor visit list | `domain/metrics` (doctor ranking), consumed by CAP-3/4 only | AD-1, AD-6" — basis for no `api/` route existing for this story, and for `DoctorVisitListService` living in `domain/metrics.py`)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-1] (dependency direction; domain service constructed from ports only)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-6] ("Source System ingestion is a contract" — `Doctor` rows arrive via the same staged/validated/transformed/upserted pipeline Story 2.1 built; this story only reads what's already there)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Core-entity relationships] ("`Doctor.Territory` is a plain attribute, not a modeled entity" — confirms territory filtering is a simple equality match, not a join)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#Information Architecture] ("Doctor Visit Prioritization (FR-5) has no dedicated portal screen... `GET /doctors`... backs report generation, not an admin-facing view... does not invent a Doctors screen" — basis for Task 3's explicit non-scope, and for flagging the stale `GET /doctors` phrase as superseded by ARCHITECTURE-SPINE.md's `api/`-free CAP-7 row)
- [Source: _bmad-output/specs/spec-growthtrack/entities.md#Doctor] (DoctorID, Name, Territory, Priority — field names only, no types/constraints, already resolved by Story 2.1's schema)
- [Source: _bmad-output/specs/spec-growthtrack/sample-whatsapp-report.md] ("Top Doctors:" condensed names-only list — confirms the eventual Epic 4 report consumption shape, out of this story's scope)
- [Source: domain/models.py#Doctor] (existing dataclass — no changes needed, read-only consumption)
- [Source: domain/metrics.py] (existing `DashboardMetricsService`/`BrandPerformanceService`/`_aggregate_company_wide`/`_classify_brands` — the module and isolated-default-function pattern this story extends a third time)
- [Source: ports/doctors.py], [adapters/persistence/doctors.py] (existing write-only `upsert_many` shape this story extends with a read method, same as Story 2.3 did for `ports/brand_performance.py`/`adapters/persistence/brand_performance.py`)
- [Source: ports/brand_performance.py], [adapters/persistence/brand_performance.py] (the `list_all` port/adapter shape this story's `Doctor` equivalent mirrors exactly)
- [Source: tests/domain/test_brand_performance_service.py] (hand-written `FakeBrandPerformanceRepository` convention, tie-break/empty/delegate test shapes this story's `test_doctor_visit_list_service.py` mirrors)
- [Source: tests/adapters/persistence/test_brand_performance_repository.py] (existing `list_all` test conventions this story's `test_doctor_repository.py` extends)
- [Source: tests/domain/test_ingestion_service.py#FakeDoctorRepository] (existing test double needing one new stub method once `DoctorRepository` gains `list_all` — same fix Story 2.3 already applied to `FakeBrandPerformanceRepository` in this same file)
- [Source: tests/conftest.py] (`_clean_tables` already covers `doctors` from Story 2.1 — no change needed)
- [Source: _bmad-output/implementation-artifacts/2-3-brand-performance-analytics.md#Dev Notes, #Review Findings] (the `_classify_brands` isolated-default-function precedent this story's `_rank_doctors_for_territory` follows; the `_to_domain`-as-free-function and `FakeBrandPerformanceRepository`-stub-method Review Findings this story implements correctly from the start rather than repeating)
- [Source: _bmad-output/implementation-artifacts/2-1-nightly-sales-reference-data-ingestion.md#Dev Notes] (`doctors` as a current-snapshot-only table, no history — basis for `list_all`'s simple unfiltered read; explicit anticipation of this story's "verify without a screen" posture)

### Review Findings

- [x] [Review][Patch] Tie-break non-determinism in `_rank_doctors_for_territory` — no final sort key beyond `(priority, name)`, so doctors sharing identical territory+priority+name have unstable relative order across calls [domain/metrics.py:237]
- [x] [Review][Patch] `test_rank_doctors_for_territory_ties_broken_by_doctor_name_and_both_retained` is tautological — calls the pure function twice on the same input list object, so it never actually exercises cross-call determinism [tests/domain/test_doctor_visit_list_service.py:77]
- [x] [Review][Patch] Territory filter uses exact case/whitespace-sensitive string equality with no normalization — a casing/whitespace mismatch silently yields an empty result [domain/metrics.py:254]
- [x] [Review][Patch] Repository `list_all` test never asserts the `id` field round-trips through `_to_domain` — only `external_doctor_id`/`territory`/`priority` are checked [tests/adapters/persistence/test_doctor_repository.py:102]
- [x] [Review][Defer] `list_all()` has no transactional/snapshot coordination with an in-progress `upsert_many()` ingestion batch, so a concurrent read could see a partially-updated snapshot — deferred, pre-existing (shared read-without-locking pattern with `BrandPerformanceService`/`DashboardMetricsService`, not introduced by this diff) [adapters/persistence/doctors.py:80]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

- `uv run pytest tests/domain/test_doctor_visit_list_service.py tests/adapters/persistence/test_doctor_repository.py tests/domain/test_ingestion_service.py -q` — 21 passed (this story's new/extended tests).
- `uv run pytest -q` (full suite, real `postgres` test container) — 196 passed, 1 pre-existing warning, 0 failures.
- `uv run ruff check .` — all checks passed, no findings.
- `uv run mypy .` — 8 pre-existing errors remain, all in files this story never touches (`tests/domain/test_password_reset_service.py`, `test_bootstrap_service.py`, `test_auth_service.py`, `tests/api/test_auth_routes.py`) — confirmed identical before/after this story's changes via `git stash`. No new errors from this story's changes.
- `uv run lint-imports` — 2 contracts kept, 0 broken (AD-1: `domain` depends only on `ports`; `ports` stays framework/adapter-free).

### Completion Notes List

- Implemented all 4 tasks: `Doctor` read-side port/adapter `list_all` with a module-level `_to_domain` free function from the start (Task 1); `DoctorEntry`/`DoctorVisitListService`/`_rank_doctors_for_territory` domain computation in `domain/metrics.py` (Task 2); confirmed explicit non-scope — no `api/` route, no `web/` component (Task 3, verified via grep of `api/` for any doctor reference — none found); full domain-service and repository-level test coverage (Task 4).
- All 4 ACs implemented. AC #4's verification posture (no portal screen, tests-only) is satisfied by Task 4's `tests/domain/test_doctor_visit_list_service.py` and the extended `tests/adapters/persistence/test_doctor_repository.py`.
- Ranking direction (`_rank_doctors_for_territory`, ascending `priority` = visit first) implemented as the story's own flagged-but-not-blocking assumption, isolated in its own pure function per the story's Dev Notes — a future direction flip is a one-line change.
- `tests/domain/test_ingestion_service.py`'s existing `FakeDoctorRepository` test double needed one new stub method (`list_all`, `raise NotImplementedError`) to stay instantiable now that Task 1 added a new abstract method to `DoctorRepository` — same fix Story 2.3 already applied to `FakeBrandPerformanceRepository` in this same file for the identical reason, not a scope change to Story 2.1's ingestion tests.
- `adapters/persistence/doctors.py#_to_domain` implemented as a module-level free function (not a `@staticmethod`) from the start, per Story 2.3's Review Findings guidance in this story's Dev Notes.
- No API route, no frontend component, no Alembic migration, and no `config.py` change were added — all confirmed out of scope per AC #3 and Task 3's explicit non-scope note.

### File List

**New:**
- `tests/domain/test_doctor_visit_list_service.py`

**Modified:**
- `ports/doctors.py`
- `adapters/persistence/doctors.py`
- `domain/metrics.py`
- `tests/adapters/persistence/test_doctor_repository.py`
- `tests/domain/test_ingestion_service.py`

## Change Log

- 2026-07-19: Implemented Story 2.4 end-to-end — `Doctor` read-side port/adapter `list_all`, ordered by territory ascending then priority ascending, with `_to_domain` as a module-level free function (Task 1); `DoctorEntry`/`DoctorVisitListService`/`_rank_doctors_for_territory` domain computation in `domain/metrics.py`, ranking ascending-priority-first per the story's flagged (non-blocking) assumption (Task 2); confirmed no `api/` route or `web/` component added, per AC #3's Daily-Report-only, no-portal-screen scope (Task 3); full domain-service and repository-level test coverage, including tie-break, empty-repository, and cross-territory-exclusion cases (Task 4). Full backend suite (196 tests), ruff, import-linter all pass clean; mypy pre-existing failures confirmed unrelated to this story via before/after diff.
