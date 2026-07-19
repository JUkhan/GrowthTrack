---
baseline_commit: 7aad716
---

# Story 2.3: Brand Performance Analytics

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want to see Top Brands, Low-Performing Brands, and Focus Brands computed from current sales data,
so that I know which brands are winning, lagging, or need a push right now.

## Acceptance Criteria

1. **Given** a current sales dataset, **when** brand rankings are computed, **then** all three lists (Top Brands, Low-Performing Brands, Focus Brands) are produced from one computation shared by the Dashboard and the (future, Epic 4) Daily Report — they never disagree. [Source: epics.md#Story 2.3, ARCHITECTURE-SPINE.md#Capability → Architecture Map CAP-6]
2. **Given** a brand list entry, **when** displayed, **then** it includes Brand Name, Sales, Rank, and Growth — the full field set, not the condensed names-only form the (future) WhatsApp report will use. [Source: epics.md#Story 2.3, prd.md#FR-4, prd.md#§4.7 "Brand and doctor entries in the report are condensed to names only... the full field set... remains available on the Dashboard"]
3. **Given** the Dashboard's Brand Performance section, **when** it renders, **then** it appears as an additional section beyond the seven core fields Story 2.2 built — a page extension, not a rebuild. [Source: epics.md#Story 2.3, epics.md#Story 2.2 Dev Notes "central scope boundary"]
4. **Given** the ranking thresholds that define "top," "low-performing," and "focus" brands are unconfirmed (neither source SRS defines them — a business decision, not an engineering guess per PRD §4.3), **when** this story is picked up for implementation, **then** implementation proceeds using the flagged, isolated default in Dev Notes below (so Epic 2 is not fully blocked and Epic 4 has something to build on), but **this story is not marked `done`** until a business/product stakeholder confirms both the threshold counts and the classification rule — track as a pre-implementation-sign-off blocker, not a silent default. This continues the exact posture Story 2.1 (cron trigger time, ingestion mechanism) and Story 2.2 (AC #6, aggregation formula) already established for this project's unconfirmed-business-decision class of open question. [Source: epics.md#Story 2.3 AC, prd.md#§4.3 footnote]

## Tasks / Subtasks

- [x] Task 1: Extend the `BrandPerformance` read-side port + adapter (AC: #1, #2)
  - [x] `ports/brand_performance.py` — add one abstract method alongside the existing `upsert_many`:
    ```python
    @abstractmethod
    async def list_all(self) -> list[Any]:
        """All current BrandPerformance rows (the table is a current-snapshot,
        not a time series — Story 2.1's Dev Notes). Ordered by rank ascending.
        Empty list when the table has never been populated, never None."""
        ...
    ```
    `Any`-typed, matching this port's existing `upsert_many` style (domain-shaped row, `ports/` can't import `domain.models` — import-linter contract).
  - [x] `adapters/persistence/brand_performance.py` — implement `list_all` on `SqlAlchemyBrandPerformanceRepository`: `SELECT * FROM brand_performance ORDER BY rank ASC`, mapped to `domain.models.BrandPerformance` via a `_to_domain`-style free function (adapters import `domain.models` freely — only `ports/` is import-linter-restricted, per `adapters/persistence/sales_data.py`'s existing precedent).
  - [x] No Alembic migration needed — `brand_performance` already exists from Story 2.1; this task only adds a read method over an existing table.

- [x] Task 2: `domain/metrics.py` — brand ranking/classification computation (AC: #1, #2, #4)
  - [x] Add to the existing module (co-located with `DashboardMetricsService` — the Architecture spine's Capability map fixes CAP-6 "Brand analytics" as living in `domain/metrics`, same as CAP-2's Dashboard summary):
    ```python
    @dataclass
    class BrandEntry:
        brand_name: str
        sales: Decimal
        rank: int
        growth_pct: Decimal

    @dataclass
    class BrandPerformanceSummary:
        top_brands: list[BrandEntry]
        low_performing_brands: list[BrandEntry]
        focus_brands: list[BrandEntry]

    class BrandPerformanceService:
        def __init__(
            self,
            brand_performance: BrandPerformanceRepository,
            top_n: int,
            low_performing_n: int,
            focus_n: int,
        ) -> None: ...

        async def get_summary(self) -> BrandPerformanceSummary: ...
    ```
    Constructed with the port only (never a concrete adapter — AD-1). Deliberately a **separate class** from `DashboardMetricsService`, not a method added to it — CAP-6 is explicitly a separate capability from CAP-2, "consumed by CAP-2 **and** CAP-3/4" per the Capability map: Epic 4's Daily Report generation (not yet built) will construct and call `BrandPerformanceService` directly from `domain/notifications`, with no dependency on the Dashboard API or `DashboardMetricsService` at all. Keeping it a standalone service is what makes that reuse a straight import, not a refactor.
  - [x] **`_classify_brands` — this is AC #4's flagged pre-sign-off default. Isolate it as its own small pure function, exactly like Story 2.2's `_aggregate_company_wide`, so swapping the rule later is a one-function change:**
    ```python
    def _classify_brands(
        rows: list[BrandPerformance], top_n: int, low_performing_n: int, focus_n: int
    ) -> BrandPerformanceSummary:
        """[ASSUMPTION — CONFIRM, epics.md Story 2.3 AC #4 / PRD §4.3 footnote]
        Neither source SRS defines what makes a brand "top," "low-performing,"
        or "focus" — this is a business decision, not an engineering guess,
        and epics.md explicitly says so. This function implements the most
        defensible engineering default so Epic 2 isn't fully blocked and
        Epic 4 has a working BrandPerformanceService to build on, but it MUST
        be confirmed by a business/product stakeholder before this story is
        marked done (AC #4) — do not describe this as "resolved" anywhere.

        Two genuinely open sub-questions this default resolves, both flagged:
        1. Threshold counts (top_n/low_performing_n/focus_n) — arbitrary
           until confirmed; this story's default is 5/5/5 (config.py).
        2. Whether the three lists are mutually exclusive. The PRD glossary
           reads "classified as Top Brand, Low-Performing Brand, or Focus
           Brand" (singular "or"), suggesting one classification per brand,
           not three independently-computed lists that could overlap. This
           function treats them as mutually exclusive for exactly that
           reason: Top N (best `rank`) is selected first; Low-Performing N
           is the worst-`rank` brands among what's LEFT after removing Top;
           Focus N is the most-negative-`growth_pct` brands among what's
           left after removing Top and Low-Performing. A brand already
           ranked "Top" can never also show up as "Focus" — which would be
           a confusing, self-contradicting Dashboard state.

        "Focus Brand" specifically (the vaguest of the three, no PRD
        definition at all) is read as "meaningfully declining but not
        already the worst performer" (growth_pct < 0, among the
        not-already-classified remainder) — distinct from Low-Performing
        (already at the bottom of `rank`, possibly beyond an easy save) and
        distinct from Top (already winning). This reading treats "Focus" as
        an early-intervention signal, which is the only version of "needs a
        push right now" that adds information beyond the other two lists.

        `rank` here is the Source-System-ingested overall performance rank
        (Story 2.1), not sales-recomputed — ascending rank = better.
        """
        by_rank = sorted(rows, key=lambda r: (r.rank, r.brand_name))
        top = by_rank[:top_n]
        top_ids = {r.external_brand_id for r in top}
        remaining_after_top = [r for r in by_rank if r.external_brand_id not in top_ids]
        low = sorted(remaining_after_top, key=lambda r: (-r.rank, r.brand_name))[:low_performing_n]
        low_ids = {r.external_brand_id for r in low}
        remaining_after_low = [r for r in remaining_after_top if r.external_brand_id not in low_ids]
        focus = sorted(
            (r for r in remaining_after_low if r.growth_pct < 0),
            key=lambda r: (r.growth_pct, r.brand_name),
        )[:focus_n]

        def _to_entry(r: BrandPerformance) -> BrandEntry:
            return BrandEntry(brand_name=r.brand_name, sales=r.sales, rank=r.rank, growth_pct=r.growth_pct)

        return BrandPerformanceSummary(
            top_brands=[_to_entry(r) for r in top],
            low_performing_brands=[_to_entry(r) for r in low],
            focus_brands=[_to_entry(r) for r in focus],
        )
    ```
  - [x] `get_summary()` body: `rows = await self._brand_performance.list_all()`; `return _classify_brands(rows, self._top_n, self._low_performing_n, self._focus_n)`.
  - [x] Do **not** touch `DashboardMetricsService`, `_aggregate_company_wide`, or any of Story 2.2's seven-field logic — this task is purely additive to `domain/metrics.py`.
  - [x] Do **not** build any Doctor visit list logic here — per epics.md Story 2.4, that's Daily-Report-only and out of this story's scope entirely.

- [x] Task 3: `api/dashboard/` route extension (AC: #1, #2, #3)
  - [x] Add to the existing `api/dashboard/routes.py` (do not create a new router package — this stays under the same `/dashboard` prefix Story 2.2 established):
    ```python
    class BrandEntryResponse(BaseModel):
        brand_name: str
        sales: Decimal
        rank: int
        growth_pct: Decimal

    class BrandPerformanceResponse(BaseModel):
        top_brands: list[BrandEntryResponse]
        low_performing_brands: list[BrandEntryResponse]
        focus_brands: list[BrandEntryResponse]
    ```
  - [x] `GET /dashboard/brand-performance` — a **separate** endpoint from `/dashboard/summary`, not a field added to `DashboardSummaryResponse`. Reasons: (a) FR-3's SM-2 3-second budget is scoped to the seven core fields specifically — bundling brand ranking into the same response risks that budget for a section with no stated latency requirement of its own; (b) epics.md's own AC split treats Story 2.3 as *extending* the Dashboard page, not the summary payload; (c) Epic 4's Daily Report will need the same `BrandPerformanceService` output independently of whatever `/dashboard/summary` returns.
  - [x] Auth: `current_user: User = Depends(get_current_user)`, identical to `summary` — no inline check, same shared AD-8 dependency.
  - [x] Handler body: construct `BrandPerformanceService` with `SqlAlchemyBrandPerformanceRepository(session)` and the three `top_n`/`low_performing_n`/`focus_n` values from `config.py` (Task 5), call `get_summary()`, map the dataclass to the response model. Pure read, no `session.commit()`.
  - [x] Money/percentage fields stay `Decimal`-typed (not `float`, not manually `str`-ed) — Story 2.2 already established this precedent for this exact codebase; `sales`/`growth_pct` follow it, not a new pattern.
  - [x] No `api/main.py` change needed — `dashboard_router` is already registered; this is a second route on the same router.

- [x] Task 4: Proxy wiring for the new endpoint (AC: #1)
  - [x] `web/vite.config.ts` — add `'/dashboard/brand-performance': 'http://localhost:8000'` as its own entry in `server.proxy`, alongside the existing `'/dashboard/summary'` entry. **Do not** widen the existing entry to a bare `'/dashboard'` prefix — Story 2.2's own Review Findings fixed a bug where a broad `/dashboard` proxy prefix collided with the frontend's own `/dashboard` page route; each new API path gets its own exact-match key, matching that established convention.
  - [x] `docker/nginx/nginx.conf` — **no change needed.** The existing `location /dashboard/ { proxy_pass http://api:8000; ... }` block (Story 2.2) is a path-prefix match, so it already covers `/dashboard/brand-performance` alongside `/dashboard/summary`. Do not add a second `/dashboard/` location block — Nginx will reject it as a duplicate.

- [x] Task 5: Config (AC: #4)
  - [x] `config.py` — add to `Settings`, following the exact `[ASSUMPTION — CONFIRM]` comment convention already used for `source_system_import_dir`/`nightly_import_cron_hour`:
    ```python
    # [ASSUMPTION — CONFIRM, epics.md Story 2.3 AC #4 / PRD §4.3 footnote]
    # Neither the PRD nor epics.md define how many brands belong in each of
    # Top/Low-Performing/Focus — a business decision, not an engineering
    # call. 5/5/5 is this story's own placeholder default (see
    # domain/metrics.py's _classify_brands docstring for the full
    # reasoning). Must be confirmed by a business/product stakeholder
    # before this story is marked done — not a silent default.
    brand_top_n: int = Field(default=5, gt=0)
    brand_low_performing_n: int = Field(default=5, gt=0)
    brand_focus_n: int = Field(default=5, gt=0)
    ```

- [x] Task 6: Frontend `BrandPerformanceSection` (AC: #2, #3)
  - [x] New component `web/src/components/BrandPerformanceSection.tsx` — extracted rather than inlined into `DashboardPage.tsx` (unlike Team Performance, which stayed inline in Story 2.2): three lists × up to 5 rows each is enough content that inlining would make `DashboardPage.tsx` hard to scan, and a standalone component gets its own focused test file. Props: `{ data: BrandPerformanceSummary | null; loading: boolean; error: boolean; onRetry: () => void }` (mirrors the `summaryError`/retry shape `DashboardPage.tsx` already uses for `/dashboard/summary`, so the two sections behave consistently).
  - [x] Layout: three `Paper` sections (or MUI `Card`), one per list, each with an `h2`-equivalent heading ("Top Brands" / "Low-Performing Brands" / "Focus Brands") and a list of rows. **A row shows Brand Name, Sales (`formatCrBdt`), Rank (`#N`), and Growth % — all four fields, not just name + tag.** `mockups/dashboard.html`'s `.brand-row` only shows name + a `.tag` because its content is transcribed verbatim from `sample-whatsapp-report.md` (the condensed, names-only WhatsApp format) — AC #2 and PRD §4.7 are explicit that the Dashboard, unlike the report, shows the full field set. Do not copy the mock's condensed row shape here; it documents the wrong source's convention for this story's screen.
  - [x] No per-row classification tag/badge is needed — each row already sits under a heading naming its list ("Top Brands" section header conveys what `.tag.top` conveyed in the two-entry mock); a redundant per-row badge would be noise once there are three headed sections instead of one flat list.
  - [x] Growth % per row: reuse the existing `StatusBadge` success/error + up/down-arrow pairing (`StatTile`'s trend prop already establishes this exact pattern in `DashboardPage.tsx` for the headline Growth % tile) — direction from `growth_pct >= 0`, label via `formatPercent`. Consistent trend treatment across the whole Dashboard, not a new one-off style for this section.
  - [x] Loading state: skeleton rows (reuse MUI `Skeleton variant="rounded"`, same primitive `StatTile`'s `loading` prop already uses) for all three sections together while the fetch is in flight — this section has its own independent loading/skeleton state, separate from Story 2.2's seven-field skeleton batch (which is explicitly scoped to the seven core fields only; Brand Performance is an "additional section," per epics.md's own AC framing, not part of that batch).
  - [x] Error state: same `Alert severity="error"` + Retry button pattern `DashboardPage.tsx` already uses for the `/dashboard/summary` fetch (Story 2.2 Review Findings fixed exactly this gap for that fetch — don't reintroduce the same silently-swallowed-error gap for this new one).
  - [x] Empty state (a list with zero entries — genuinely possible if `brand_performance` hasn't been ingested yet, or has fewer real brands than a threshold): direct copy per list, e.g. "No brands classified yet" — **no primary action**, unlike UX-DR16's general empty-state pattern (which pairs empty state with one action button). Brand Performance data arrives via nightly ingestion (Story 2.1); there is no admin-initiated action that would populate it, the same reasoning already applied to the Dashboard's neutral "No sends yet" Notification Status tile.
  - [x] `web/src/pages/DashboardPage.tsx`: add a second `useEffect` fetching `GET /dashboard/brand-performance` on mount (once authenticated), independent of the summary fetch — same `apiFetch` helper, own `brandPerformance`/`brandPerformanceError`/`brandPerformanceRetryCount` state trio, mirroring the existing summary-fetch state shape exactly. Render `<BrandPerformanceSection>` below the seven-field grid (Story 2.2 Dev Notes: "Build the Dashboard layout so a later section can be appended below/beside the seven-field grid" — this is that later section).

- [x] Task 7: Tests (AC: #1, #2, #3, #4)
  - [x] `tests/domain/test_brand_performance_service.py` — new file, hand-written `FakeBrandPerformanceRepository` (no mocking library, per this repo's established convention from `test_dashboard_metrics_service.py`/`test_ingestion_service.py`). Cases:
    - More brands than `top_n + low_performing_n` exist → Top N are the N lowest `rank` values, Low-Performing N are the N highest `rank` values among the rest, and the two lists never share a brand.
    - A brand with negative `growth_pct` that isn't already Top or Low-Performing appears in Focus; a brand with negative `growth_pct` that IS already in Top or Low-Performing does **not** also appear in Focus (mutual-exclusivity assertion — the core of AC #4's classification-rule assumption).
    - Fewer brands exist than `top_n` → Top gets all of them, Low-Performing/Focus get whatever's left (no `IndexError`, no fabricated rows).
    - Zero brands (`list_all()` returns `[]`) → all three lists empty, no exception.
    - All brands have non-negative `growth_pct` → Focus list is empty (never includes a non-declining brand).
    - Sort stability: two brands sharing the same `rank` → both included, tie broken by `brand_name`, deterministic across repeated calls.
  - [x] `tests/adapters/persistence/test_brand_performance_repository.py` — extend with a `list_all` case: multiple seeded rows returned ordered by `rank` ascending; empty table returns `[]`, not `None`.
  - [x] `tests/api/test_dashboard_routes.py` — extend with `GET /dashboard/brand-performance` cases: without a session → 401 (`unauthorized` envelope, matching `summary`'s existing case); with a seeded session and seeded `brand_performance` rows → 200 with `top_brands`/`low_performing_brands`/`focus_brands`, each entry's `sales`/`growth_pct` arriving as JSON strings (Decimal-over-JSON precedent, same spot-check style as the existing `summary` test).
  - [x] `tests/conftest.py` — no change needed; `_clean_tables` already covers `brand_performance` (added in Story 2.1).
  - [x] `web/src/components/BrandPerformanceSection.test.tsx` — new file. Cases: `loading` renders skeletons in all three sections; resolved data renders Brand Name/Sales/Rank/Growth for each list; an empty list renders its "No brands classified yet" copy with no action button; `error` renders the Alert + Retry button and clicking Retry calls `onRetry`.
  - [x] `web/src/pages/DashboardPage.test.tsx` — extend: authenticated + `/dashboard/brand-performance` resolved renders the section below the seven-field grid; a `/dashboard/brand-performance` failure shows that section's own error state without affecting the seven-field tiles (the two fetches are independent — verifies Task 6's separation).
  - [x] `uv run lint-imports` after this story's changes — confirm `ports/brand_performance.py` stays `domain`-free and `domain/metrics.py`'s new code only imports from `ports/`.

### Review Findings

- [x] [Review][Decision] Per-list headings render as `h3`, not the spec's literal "h2-equivalent" — literal spec fidelity vs. correct heading nesting. Task 6 explicitly says each of the three list headings ("Top Brands"/"Low-Performing Brands"/"Focus Brands") should be an "`h2`-equivalent heading." `BrandPerformanceSection.tsx` renders them as `<Typography variant="subtitle1" component="h3">`, one level below the parent "Brand Performance" section title, which already occupies `h2` (`<Typography variant="h6" component="h2">`). Following the spec literally (four sibling `h2`s: one section title + three list headings) would flatten the heading hierarchy versus the current, arguably more standard `h2 → h3` nesting. **Resolved:** keep `h3` as implemented — the spec's "h2-equivalent" wording is treated as loose/approximate; the current nested `h2 → h3` hierarchy is standard semantic HTML and better for accessibility. No code change. [web/src/components/BrandPerformanceSection.tsx]

- [x] [Review][Patch] Loading skeletons and the error Alert can render simultaneously in Brand Performance, and stay stuck that way — `loading` is derived purely as `brandPerformance === null` (DashboardPage.tsx:320), independent of `brandPerformanceError`. Since a failed fetch never sets `brandPerformance`, the very first failure leaves both `loading` and `error` true at once — skeleton rows render alongside the "Couldn't load..." Alert, with no test covering this combination. If a fetch fails *after* a prior success, stale data renders under the error banner with no staleness indicator. Fix: `loading={brandPerformance === null && !brandPerformanceError}`, and clear `brandPerformanceError` when a new fetch attempt starts. Note: the pre-existing `/dashboard/summary` fetch (Story 2.2, untouched by this diff) has the identical bug — out of scope here, worth a follow-up. [web/src/pages/DashboardPage.tsx:318-323]

- [x] [Review][Patch] `external_brand_id` is dropped from `BrandEntry`/`BrandEntryResponse`; the frontend list `key` uses `brand_name`, which has no DB uniqueness constraint (only `external_brand_id` does — `adapters/persistence/brand_performance.py:28`). Two different brands sharing a display name (a plausible source-data quality issue) would collide as a React key within the same list, causing duplicate/missing row rendering. Fix: thread `external_brand_id` through `BrandEntry` → `BrandEntryResponse` → the frontend type, and use it as the row key. [domain/metrics.py, api/dashboard/routes.py, web/src/components/BrandPerformanceSection.tsx]

- [x] [Review][Patch] Row field order (Rank before Sales) deviates from Task 6's literal "Brand Name, Sales, Rank, and Growth %" sequence — purely cosmetic, all four fields are present and AC #2 doesn't require a specific order, but trivial to reorder if literal fidelity is wanted. [web/src/components/BrandPerformanceSection.tsx]

- [x] [Review][Patch] `_to_domain` is implemented as a `@staticmethod` on `SqlAlchemyBrandPerformanceRepository` rather than the module-level free function Task 1 describes ("a `_to_domain`-style free function"). No functional difference either way; trivial to move to module scope for literal spec fidelity. [adapters/persistence/brand_performance.py]

- [x] [Review][Patch] Tie-break test coverage gaps: the one existing tie-break test (`test_classify_brands_ties_broken_by_brand_name_deterministically`) uses `top_n=1`, which can only prove the alphabetical winner — not Task 7's literal "both included" requirement — and the identical tie-break sort keys used for `low_performing_brands`/`focus_brands` have zero equivalent test coverage. [tests/domain/test_brand_performance_service.py]

- [x] [Review][Patch] `test_brand_performance_service_get_summary_delegates_to_classify_brands` never asserts on `focus_brands`, leaving one-third of `get_summary()`'s output unverified at the service-integration level. [tests/domain/test_brand_performance_service.py]

- [x] [Review][Patch] Hardcoded skeleton row count (3) in `BrandListSkeleton` doesn't match the configured default bucket size (`brand_top_n`/`brand_low_performing_n`/`brand_focus_n` = 5) — causes a minor layout shift once real data (up to 5 rows/list) resolves. [web/src/components/BrandPerformanceSection.tsx]

- [x] [Review][Patch] `_classify_brands` doesn't guard against negative `top_n`/`low_performing_n`/`focus_n` — not reachable today (Settings enforces `gt=0` at the only production call site), but this story's own Dev Notes say Epic 4's Daily Report will call `BrandPerformanceService` directly, so the guard isn't purely theoretical. Cheap defensive addition: raise `ValueError` on negative inputs. [domain/metrics.py:176-189]

- [x] [Review][Defer] Exactly-0% growth renders with the green "up" badge/arrow (`Number(entry.growth_pct) >= 0` treats 0 as non-negative) — no neutral state exists. Not specified anywhere in this story's ACs or the design docs; a design call for a future story. — deferred, pre-existing [web/src/components/BrandPerformanceSection.tsx]

## Dev Notes

- **This story's central scope boundary: Brand Performance only.** Doctor visit list (Story 2.4, Daily-Report-only, no portal screen ever) is explicitly out of scope. Story 2.2's seven-field Dashboard scaffold is not touched except for one additive render call in `DashboardPage.tsx` — its existing tests/behavior must keep passing unchanged.
- **AC #4's threshold/classification question is this story's version of the pattern Stories 2.1 and 2.2 already established for unconfirmed business decisions**: implement with a small, isolated, heavily-commented default function (`_classify_brands`, mirroring `_aggregate_company_wide`'s treatment) rather than blocking implementation outright — Epic 2 stays unblocked and Epic 4's Daily Report has a real `BrandPerformanceService` to build on. But per epics.md's explicit AC language, **do not mark this story `done`** without a business/product stakeholder confirming (a) the three threshold counts and (b) the mutual-exclusivity classification rule the isolated function encodes. Surface this prominently in the PR description — it is not merely a code comment to skim past, same posture as Story 2.2's AC #6.
- **Two distinct open questions are bundled inside AC #4, both handled in `_classify_brands`'s docstring — don't conflate them:** (1) *how many* brands per list (threshold counts — config values), and (2) *whether the lists overlap* (a brand appearing in more than one list). The PRD glossary's "classified as Top Brand, Low-Performing Brand, or Focus Brand" (singular "or") is the basis for treating them as mutually exclusive; this is this story's own reasoned interpretation, not a stated rule, and should be confirmed alongside the threshold counts.
- **No new Alembic migration.** `brand_performance` already exists (Story 2.1); this story only adds a read method (`list_all`) and one new API route reading it. If you find yourself writing a migration for this story, you've misread a task.
- **Why `/dashboard/brand-performance` is a separate endpoint, not a field on `/dashboard/summary`:** FR-3's SM-2 3-second budget applies to the seven core fields specifically; Brand Performance has no stated latency requirement of its own and epics.md's AC framing treats it as a Dashboard page *extension*, not a change to the summary payload. Keeping it a separate fetch also means Epic 4's Daily Report can call `BrandPerformanceService` directly, with zero dependency on `/dashboard/summary`'s shape.
- **`mockups/dashboard.html`'s Brand Performance section under-represents this story's actual requirement — don't copy its row shape.** The mock's `.brand-row` shows only Brand Name + a `.tag` (Top Brand/Focus Brand) because its content is transcribed verbatim from `sample-whatsapp-report.md`, the condensed WhatsApp-report format. AC #2 and PRD §4.7 are explicit that the Dashboard (unlike the report) shows the full field set: Brand Name, Sales, Rank, **and** Growth. Build the fuller row; the mock documents the report's convention, not this screen's.
- **Independent loading/error state, not bundled into Story 2.2's seven-field skeleton batch.** Story 2.2 AC #2 ("all seven fields skeleton together, never partial") is scoped strictly to the seven core fields — Brand Performance is explicitly an "additional section" per epics.md's Story 2.3 AC, so its own skeleton/error/retry cycle is expected and correct, not a violation of AC #2's spirit.
- **Vite proxy: add a new exact-match key, don't widen the existing one.** Story 2.2's own Review Findings fixed a bug from a too-broad `/dashboard` proxy prefix colliding with the frontend's `/dashboard` page route. `docker/nginx/nginx.conf` needs no change — its `location /dashboard/` block is already prefix-based and covers the new path.

### Project Structure Notes

- Modified backend files: `ports/brand_performance.py` (new `list_all` method), `adapters/persistence/brand_performance.py` (implementation), `domain/metrics.py` (new `BrandEntry`/`BrandPerformanceSummary`/`BrandPerformanceService`/`_classify_brands`, additive to Story 2.2's existing content), `api/dashboard/routes.py` (new route + response models, additive to Story 2.2's existing `summary` route), `config.py` (`brand_top_n`/`brand_low_performing_n`/`brand_focus_n`).
- New backend test file: `tests/domain/test_brand_performance_service.py`. Modified: `tests/adapters/persistence/test_brand_performance_repository.py`, `tests/api/test_dashboard_routes.py`.
- New frontend files: `web/src/components/BrandPerformanceSection.tsx`, `web/src/components/BrandPerformanceSection.test.tsx`.
- Modified frontend files: `web/src/pages/DashboardPage.tsx` (second independent fetch + render call), `web/src/pages/DashboardPage.test.tsx` (extended), `web/vite.config.ts` (new proxy entry).
- No new top-level directories; no Alembic migration; no `docker/nginx/nginx.conf` change.

### Previous Story Intelligence (from 2-2-dashboard-summary-view)

- `domain/metrics.py` already exists with `DashboardMetricsService`/`_aggregate_company_wide` — this story adds to the same file rather than creating a new one, matching the Architecture spine's Capability map (`domain/metrics` owns both CAP-2 and CAP-6).
- The isolated-pure-function-with-a-heavy-docstring pattern for an unconfirmed business default (`_aggregate_company_wide`) is directly reused here for `_classify_brands` — same shape, same "must be confirmed before done" framing, same "don't describe as resolved" instruction.
- `Decimal`-typed response fields (not `float`, not manually `str`-ed) is an established precedent from Story 2.2's `DashboardSummaryResponse` — `BrandEntryResponse.sales`/`growth_pct` follow it directly.
- The `/dashboard/summary` fetch's error-handling gap (silently swallowed failures, tiles stuck loading forever) was a Story 2.2 Review Finding, fixed with an `Alert` + Retry pattern — this story's new `/dashboard/brand-performance` fetch must ship with that same pattern from the start, not repeat the gap and need its own review-cycle fix.
- The Vite dev-proxy collision Review Finding (broad `/dashboard` prefix vs. the frontend's own `/dashboard` page route) means every new `/dashboard/*` API path needs its own exact-match proxy key — this story's Task 4 follows that corrected convention directly rather than the original (buggy) broad-prefix approach.
- `StatTile`'s `loading` prop and `StatusBadge`'s `neutral`/trend-pairing patterns are established, additive-only components — this story's `BrandPerformanceSection` reuses `StatusBadge`'s existing success/error trend pairing for per-row Growth %, it does not invent a new indicator style.

### Git Intelligence

- `HEAD` is `7aad716` ("story 2.2"), working tree clean.
- Migration chain is unchanged by this story (still ends at Story 2.1's `e054c35b938f` revision, confirmed unaffected by Story 2.2 too) — confirms Task 1's "no new Alembic migration" call.
- Commit style: one commit per logical unit of work, imperative summary line, ending with the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3: Brand Performance Analytics] (all 4 ACs, verbatim basis for this story's AC list, including the explicit pre-implementation-blocker language)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2: Dashboard Summary View] (AC establishing this story extends, not rebuilds, the seven-field page; Dev Notes' "central scope boundary" precedent)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#FR-4] (Top/Low-Performing/Focus Brands definition, "Each list entry includes Brand Name, Sales, Rank, and Growth")
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#§4.3] ("neither source SRS defines these thresholds — needs a business decision, not an engineering guess")
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#§4.7] (report condenses brand/doctor entries to names only; full field set stays on the Dashboard — basis for AC #2's row-shape requirement)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#Glossary "Brand"] ("classified as Top Brand, Low-Performing Brand, or Focus Brand" — basis for this story's mutual-exclusivity reading)
- [Source: _bmad-output/specs/spec-growthtrack/sample-whatsapp-report.md] (condensed report format `mockups/dashboard.html`'s Brand Performance section is transcribed from — explicitly the wrong source to copy this story's Dashboard row shape from)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Capability → Architecture Map] (CAP-6: `domain/metrics`, "consumed by CAP-2 and CAP-3/4" — basis for `BrandPerformanceService` being a standalone, Dashboard-independent class)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-1] (dependency direction; domain service constructed from ports only)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Deferred] ("Brand top/low/focus ranking thresholds. A business decision per PRD FR-4's note, not an engineering call" — confirms this is still open at the architecture level too)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/mockups/dashboard.html] (Brand Performance section markup/styling reference — flagged in Dev Notes as under-representing this story's actual row-content requirement)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/DESIGN.md#Components] (`status-badge` never-color-alone rule, reused for per-row Growth % trend pairing)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#Information Architecture] (Dashboard row: "plus Brand Performance (FR-4)")
- [Source: domain/metrics.py] (existing `DashboardMetricsService`/`_aggregate_company_wide` — the module and the isolated-default-function pattern this story extends)
- [Source: domain/models.py] (`BrandPerformance` dataclass — no changes needed, read-only consumption)
- [Source: ports/brand_performance.py], [adapters/persistence/brand_performance.py] (existing write-only `upsert_many` shape this story extends with a read method)
- [Source: api/dashboard/routes.py] (existing `summary` route/response-model structure this story's `brand-performance` route mirrors)
- [Source: config.py] (`Settings` field / `[ASSUMPTION — CONFIRM]`-comment conventions)
- [Source: web/src/pages/DashboardPage.tsx] (existing summary-fetch state shape, `Alert`+Retry error pattern, `StatTile`/`StatusBadge` trend-pairing usage this story's new section mirrors)
- [Source: web/src/components/StatTile.tsx], [StatusBadge.tsx] (reusable components this story's `BrandPerformanceSection` composes, does not duplicate)
- [Source: web/src/utils/format.ts] (`formatCrBdt`/`formatPercent` reused as-is for brand row figures)
- [Source: web/vite.config.ts], [docker/nginx/nginx.conf] (existing `/dashboard/summary` proxy-key precedent and prefix-based Nginx location this story's new endpoint reuses/extends correctly)
- [Source: tests/domain/test_dashboard_metrics_service.py], [tests/domain/test_ingestion_service.py] (hand-written `Fake*Repository` convention, no mocking library)
- [Source: tests/api/test_dashboard_routes.py] (existing route-test conventions this story's `brand-performance` cases extend)
- [Source: tests/adapters/persistence/test_brand_performance_repository.py] (existing `upsert_many` test conventions this story's `list_all` case extends)
- [Source: tests/conftest.py] (`_clean_tables` already covers `brand_performance` from Story 2.1 — no change needed)
- [Source: _bmad-output/implementation-artifacts/2-2-dashboard-summary-view.md#Dev Notes, #Review Findings] (the `_aggregate_company_wide` isolated-default-function precedent; the summary-fetch error-handling and Vite-proxy-collision Review Findings this story's new endpoint must not repeat)
- [Source: _bmad-output/implementation-artifacts/2-1-nightly-sales-reference-data-ingestion.md#Dev Notes] (`brand_performance` as a current-snapshot-only table, no history — basis for `list_all`'s simple unfiltered read)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

- `uv run pytest -q` against the existing real `postgres:18.4-alpine` container (`gt-test-postgres`, already running) — 184 passed, 1 pre-existing warning, 0 failures.
- `uv run ruff check .` — 1 line-length finding introduced by this story's own new code (`domain/metrics.py`), fixed; clean on recheck.
- `uv run mypy .` — 8 pre-existing errors remain, all in files this story never touches (`tests/domain/test_password_reset_service.py`, `test_bootstrap_service.py`, `test_auth_service.py`, `tests/api/test_auth_routes.py`), matching Story 2.2's own documented Debug Log exactly. No new errors from this story's changes.
- `uv run lint-imports` — 2 contracts kept, 0 broken (AD-1: `domain` depends only on `ports`; `ports` stays framework/adapter-free).
- `npm test` (Vitest) — 81 passed, 14 files (22 of them this story's own new/extended cases across `DashboardPage.test.tsx` and the new `BrandPerformanceSection.test.tsx`).
- `npm run typecheck` (`tsc -b`) — clean.
- `npm run lint` (eslint) — 1 pre-existing error in `LoginPage.tsx:36` (`react-hooks/set-state-in-effect`), confirmed via `git diff --stat` to be a file this story's changes never touch (matches Story 2.2's own documented pre-existing finding).
- `docker run --rm nginx:alpine nginx -t` against the unmodified `docker/nginx/nginx.conf` — syntax OK, confirming Task 4's "no Nginx change needed" call.

### Completion Notes List

- Implemented all 7 tasks: `BrandPerformance` read-side port/adapter (Task 1), `BrandPerformanceService`/`_classify_brands` in `domain/metrics.py` (Task 2), `GET /dashboard/brand-performance` route (Task 3), Vite proxy entry (Task 4), `config.py` threshold settings (Task 5), `BrandPerformanceSection` frontend component + `DashboardPage` wiring (Task 6), full test suite (Task 7).
- All 4 ACs implemented, including AC #4's flagged `_classify_brands` placeholder — isolated in its own pure function with an in-code `[ASSUMPTION — CONFIRM]` docstring covering both open sub-questions (threshold counts and mutual-exclusivity classification rule), per the story's explicit instruction.
- **AC #4 sign-off is still outstanding** — per the story's own Dev Notes, this story is implemented but **should not be considered fully "done"** until a business/product stakeholder confirms both (a) the three threshold counts (`brand_top_n`/`brand_low_performing_n`/`brand_focus_n`, defaulted to 5/5/5) and (b) the mutual-exclusivity classification rule `_classify_brands` encodes. This is a pre-existing-flagged business sign-off blocker, not an implementation gap — moving Status to "review" here reflects "implementation complete, ready for code review," not "AC #4 stakeholder sign-off obtained."
- `tests/domain/test_ingestion_service.py`'s existing `FakeBrandPerformanceRepository` test double needed one new stub method (`list_all`, `raise NotImplementedError`) to stay instantiable now that Task 1 added a new abstract method to `BrandPerformanceRepository` — required for that pre-existing test file to keep passing, not a scope change to Story 2.1's tests (same pattern Story 2.2 already established for its own port extensions).
- `docker/nginx/nginx.conf` required no change — its existing `location /dashboard/` block (Story 2.2) is prefix-based and already covers `/dashboard/brand-performance`; verified with `nginx -t`.
- `DashboardPage.test.tsx`'s existing shared `stubFetch` helper and 6 other inline fetch mocks were each extended with an explicit `/dashboard/brand-performance` branch (returning empty lists) so the new independent fetch resolves deterministically in every pre-existing test, rather than falling through to the generic null-body-200 catch-all — which would have surfaced a second, unrelated error/Retry state and broken several exact-count/exact-role assertions (7-skeleton count, single "Retry" button lookup) that predate this story.

### File List

**New:**
- `tests/domain/test_brand_performance_service.py`
- `web/src/components/BrandPerformanceSection.tsx`
- `web/src/components/BrandPerformanceSection.test.tsx`

**Modified:**
- `ports/brand_performance.py`
- `adapters/persistence/brand_performance.py`
- `domain/metrics.py`
- `api/dashboard/routes.py`
- `config.py`
- `web/vite.config.ts`
- `web/src/pages/DashboardPage.tsx`
- `web/src/pages/DashboardPage.test.tsx`
- `tests/adapters/persistence/test_brand_performance_repository.py`
- `tests/api/test_dashboard_routes.py`
- `tests/domain/test_ingestion_service.py`

## Change Log

- 2026-07-19: Implemented Story 2.3 end-to-end — `BrandPerformance` read-side port/adapter `list_all` (Task 1); `BrandPerformanceService`/`_classify_brands` domain computation with the mutually-exclusive Top/Low-Performing/Focus classification placeholder flagged per AC #4 (Task 2); `GET /dashboard/brand-performance` route with `Decimal`-typed response fields (Task 3); Vite proxy entry, no Nginx change needed (Task 4); `brand_top_n`/`brand_low_performing_n`/`brand_focus_n` config (Task 5); `BrandPerformanceSection` frontend component with independent loading/error/retry state, wired into `DashboardPage` below the seven-field grid (Task 6); full backend/frontend test coverage (Task 7). Full backend suite (184 tests), frontend suite (81 tests), ruff, import-linter, and `tsc` all pass clean; mypy/eslint pre-existing failures confirmed unrelated to this story. AC #4's business/product stakeholder sign-off on threshold counts and the classification rule remains outstanding per the story's own Dev Notes.
