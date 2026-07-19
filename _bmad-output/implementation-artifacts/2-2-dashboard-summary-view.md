---
baseline_commit: b8fb96519f86fdd337613c113204b607353b5ce5
---

# Story 2.2: Dashboard Summary View

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want a single dashboard summarizing Today's Sales, YTD Sales, MTD Sales, Achievement %, Growth %, team performance, and notification status,
so that I can assess sales health at a glance.

## Acceptance Criteria

1. **Given** current sales data exists, **when** I open the Dashboard, **then** all seven fields (Today's Sales, YTD Sales, MTD Sales, Achievement %, Growth %, team performance, notification status) render from `GET /dashboard/summary` within 3 seconds. [Source: epics.md#Story 2.2, prd.md#FR-3 SM-2]
2. **Given** the Dashboard is loading, **when** data hasn't arrived yet, **then** skeleton stat tiles are shown for all seven fields together — never a partial render (SM-C2: load-time optimization must never come at the cost of dropping or stubbing a field). [Source: epics.md#Story 2.2, EXPERIENCE.md#State Patterns Loading]
3. **Given** the last successful import (`ImportRun.completed_at`, Story 2.1) is older than the configured staleness window, **when** I view the Dashboard, **then** a "Data as of HH:MM" badge is shown in Asia/Dhaka local time (warning-styled, icon + label per the status-badge pattern), rather than presenting stale numbers as current; when data is fresh, the same badge shows in its neutral/success styling. [Source: epics.md#Story 2.2, EXPERIENCE.md#State Patterns Stale, ARCHITECTURE-SPINE.md#AD-6]
4. **Given** the viewport narrows below `md`, **when** I view the Dashboard, **then** stat tiles reflow to a single column without hiding any of the seven fields — order changes, presence never does. [Source: epics.md#Story 2.2, DESIGN.md, EXPERIENCE.md#Responsive]
5. **Given** no notification has been sent yet (Epic 4 not yet built), **when** the notification-status field renders, **then** it shows a neutral "No sends yet" state rather than erroring — this field's live wiring to actual send outcomes is completed in Epic 4 (Stories 4.1/4.2), which is a backward extension of this story, not a forward dependency of it. [Source: epics.md#Story 2.2]
6. **Given** the exact Achievement %/Growth % formulas are unconfirmed by a finance/business stakeholder (PRD §13 OQ#3; still listed open in `ARCHITECTURE-SPINE.md`'s Deferred section — Story 2.1's ingestion-as-given treatment was its own unconfirmed `[ASSUMPTION — CONFIRM]`, never itself ratified by a stakeholder), **when** this story is picked up for implementation, **then** implementation proceeds using the flagged defaults in Dev Notes below (so the rest of the Dashboard is not blocked), but **this story is not marked `done`** until a finance/business stakeholder confirms both (a) that Story 2.1's ingested-as-given per-team/per-day values are actually correct and (b) this story's own cross-team aggregation for the two headline tiles — track as a pre-implementation-sign-off blocker, not a silent default. [Source: epics.md#Story 2.2 AC #6, prd.md#§13 Open Question #3]

## Tasks / Subtasks

- [x] Task 1: Extend read-side repository ports + adapters (AC: #1, #3)
  - [x] `ports/sales_data.py` — add two abstract methods to `SalesDataRepository` alongside the existing `upsert_many`:
    ```python
    @abstractmethod
    async def sum_amount_in_range(self, start_date: date, end_date: date) -> Decimal:
        """Sum of sales_amount across ALL teams for date in [start_date, end_date] inclusive. 0 (never None) when no rows match."""
        ...

    @abstractmethod
    async def latest_per_team(self) -> list[Any]:
        """One SalesData-shaped row per team_id — the row with the most recent `date` for that team. Teams with zero sales_data rows are simply absent (never a fabricated zero row)."""
        ...
    ```
    `Decimal`/`date` are stdlib, not domain-shaped, so they're fine in the port signature directly (same reasoning `ports/import_runs.py`'s `datetime` params already establish) — only `latest_per_team`'s row payload needs `Any` (domain-shaped, import-linter forbids `ports` → `domain`).
  - [x] `ports/teams.py` — add:
    ```python
    @abstractmethod
    async def list_all(self) -> list[tuple[uuid.UUID, str]]: ...
    ```
    Primitive-typed (`(id, name)` pairs), matching this port's existing style — no `Any` needed since a bare id/name pair isn't domain-shaped.
  - [x] `ports/import_runs.py` — add:
    ```python
    @abstractmethod
    async def get_last_successful_completed_at(self) -> datetime | None: ...
    ```
    Primitive-typed (`datetime`), matching this port's existing style. Returns `None` only when no `ImportRun` has ever reached `succeeded` status (not yet run, or every run so far failed).
  - [x] `adapters/persistence/sales_data.py` — implement both new methods on `SqlAlchemySalesDataRepository`:
    - `sum_amount_in_range`: `SELECT COALESCE(SUM(sales_amount), 0) FROM sales_data WHERE date BETWEEN :start AND :end` (Core `select(func.coalesce(func.sum(...), 0))` — `COALESCE` is required because SQL `SUM` over zero rows is `NULL`, not `0`; returning `None` here would break Task 2's arithmetic).
    - `latest_per_team`: Postgres `DISTINCT ON (team_id) ... ORDER BY team_id, date DESC` (idiomatic "latest row per group" — do not implement this as a Python loop over `upsert_many`-style N+1 queries). Map each result row to a `domain.models.SalesData` instance via a `_to_domain`-style helper (adapters may import `domain.models` freely — only `ports/` is import-linter-restricted from it, per `adapters/persistence/import_runs.py`'s existing `from domain.models import ImportRunStatus` precedent).
  - [x] `adapters/persistence/teams.py` — implement `list_all`: `SELECT id, name FROM teams ORDER BY name`.
  - [x] `adapters/persistence/import_runs.py` — implement `get_last_successful_completed_at`: `SELECT completed_at FROM import_runs WHERE status = 'succeeded' ORDER BY completed_at DESC LIMIT 1`.
  - [x] No Alembic migration is needed for this task — every new method reads/aggregates columns Story 2.1 already created; no schema change.

- [x] Task 2: `domain/metrics.py` — dashboard summary computation (AC: #1, #3, #6)
  - [x] New module, `DashboardMetricsService`, constructed with every port from Task 1 (never a concrete adapter — AD-1):
    ```python
    @dataclass
    class TeamPerformance:
        team_id: uuid.UUID
        team_name: str
        achievement_pct: Decimal

    @dataclass
    class DashboardSummary:
        today_sales: Decimal
        ytd_sales: Decimal
        mtd_sales: Decimal
        achievement_pct: Decimal | None   # None only when there is no sales data at all yet
        growth_pct: Decimal | None
        team_performance: list[TeamPerformance]
        data_as_of: datetime | None       # UTC — Asia/Dhaka conversion happens at the presentation edge (frontend), per Consistency Conventions
        is_stale: bool

    class DashboardMetricsService:
        def __init__(
            self,
            sales_data: SalesDataRepository,
            teams: TeamRepository,
            import_runs: ImportRunRepository,
            stale_after: timedelta,
        ) -> None: ...

        async def get_summary(self, today: date, now: datetime) -> DashboardSummary: ...
    ```
    `today` (Asia/Dhaka operational-day date) and `now` (UTC) are caller-supplied, not computed inside the service via a live clock call — this keeps the service deterministically testable with fixed dates/times, matching this codebase's established pattern of callers passing time values into domain services (e.g. `ImportRunRepository.start(correlation_id, started_at)`) rather than a `Clock` port (no `Clock` port exists anywhere in `ports/` today — do not invent one for this single call site).
  - [x] `get_summary` logic, in order:
    1. `year_start = today.replace(month=1, day=1)`; `month_start = today.replace(day=1)`.
    2. `today_sales = await sales_data.sum_amount_in_range(today, today)`.
    3. `ytd_sales = await sales_data.sum_amount_in_range(year_start, today)`.
    4. `mtd_sales = await sales_data.sum_amount_in_range(month_start, today)`.
    5. `latest_rows = await sales_data.latest_per_team()`.
    6. `team_names = dict(await teams.list_all())`.
    7. `team_performance = [TeamPerformance(team_id=row.team_id, team_name=team_names.get(row.team_id, row.team_id.hex), achievement_pct=row.achievement_pct) for row in latest_rows]`, sorted by `team_name` for stable rendering order.
    8. `achievement_pct, growth_pct = _aggregate_company_wide(latest_rows)` — see below.
    9. `data_as_of = await import_runs.get_last_successful_completed_at()`.
    10. `is_stale = data_as_of is None or (now - data_as_of) > stale_after`.
  - [x] **`_aggregate_company_wide` — this is AC #6's flagged pre-sign-off default, isolate it as its own small pure function so swapping the formula later is a one-function change:**
    ```python
    def _aggregate_company_wide(rows: list[SalesData]) -> tuple[Decimal | None, Decimal | None]:
        """[ASSUMPTION — CONFIRM, epics.md Story 2.2 AC #6 / PRD §13 OQ#3]
        Sales-amount-weighted average of each team's latest achievement_pct/
        growth_pct. These per-team/per-row values are already ingested
        as-given from the Source System per Story 2.1's Dev Notes — but that
        was Story 2.1's own unconfirmed `[ASSUMPTION — CONFIRM]`, never
        ratified by a finance/business stakeholder, and `ARCHITECTURE-SPINE.md`'s
        Deferred section still lists "exact Achievement %/Growth % formulas"
        as entirely open. Do not treat Story 2.1's shipped behavior as
        authoritative confirmation — it is an existing, load-bearing
        implementation this story builds on (rewriting Story 2.1 is out of
        this story's scope), but it still needs sign-off. On top of that,
        this function adds a second, genuinely new open question: how
        per-team figures roll up into ONE company-wide headline number.
        sample-whatsapp-report.md proves this isn't a naive average
        (MTD Achievement 40% != mean of Team A/B/C's 45/50/40, which is 45) —
        some non-trivial weighting is in play upstream that this story cannot
        reverse-engineer from the sample alone. Sales-weighted average is the
        most defensible engineering default (bigger teams influence the
        headline more, directionally right for a company-wide figure) but is
        NOT verified against the sample. Both halves — the per-row ingestion
        treatment AND this aggregation — MUST be confirmed by a
        finance/business stakeholder before this story is marked done (AC #6).
        """
        total_sales = sum((row.sales_amount for row in rows), Decimal(0))
        if not rows or total_sales == 0:
            return None, None
        achievement = sum((row.achievement_pct * row.sales_amount for row in rows), Decimal(0)) / total_sales
        growth = sum((row.growth_pct * row.sales_amount for row in rows), Decimal(0)) / total_sales
        return achievement, growth
    ```
  - [x] Do **not** implement Brand Performance computation/rendering in this story. FR-3's Dashboard "seven fields" and FR-4's Brand Performance section are two separate ACs split across two stories on purpose: epics.md's Story 2.3 AC explicitly owns "the Dashboard's Brand Performance section... appears as an additional section beyond the seven core fields" — i.e. Story 2.3 *adds to* the page this story builds. Build the Dashboard layout so a later section can be appended below/beside the seven-field grid, but do not fetch, rank, or render `BrandPerformance` data here.
  - [x] Do **not** build a Doctor visit list screen. Per epics.md Story 2.4, it is Daily-Report-only and never gets a portal screen.

- [x] Task 3: `api/dashboard/` route (AC: #1, #3, #5)
  - [x] New package `api/dashboard/__init__.py` + `api/dashboard/routes.py`, mirroring `api/auth/routes.py`'s structure (`APIRouter(prefix="/dashboard", tags=["dashboard"])`).
  - [x] `GET /dashboard/summary` — **not** `GET /dashboard` (bare). The frontend's own page route is `/dashboard` (Task 5); if the API resource were also bare `/dashboard`, Nginx/Vite proxy routing (Task 4) could not distinguish "browser navigating to the SPA page" from "SPA calling the API" on the same path. `/summary` under the `/dashboard` prefix keeps the same prefix-proxy pattern `/auth/` already uses cleanly.
  - [x] Auth: `current_user: User = Depends(get_current_user)` — the existing shared AD-8 dependency, no inline check, exactly like every other portal route.
  - [x] Handler body: compute `now = datetime.now(UTC)`, `today = now.astimezone(ZoneInfo("Asia/Dhaka")).date()` (stdlib `zoneinfo.ZoneInfo` — no new dependency; this is the one and only place the Asia/Dhaka *operational day* is derived, per Consistency Conventions: "Operational Day is a presentation/business-logic concept, never a stored timezone"). Construct `DashboardMetricsService` with the three `SqlAlchemy*Repository` adapters and `stale_after=timedelta(hours=settings.dashboard_stale_after_hours)` (Task 6), call `get_summary(today, now)`. This is a pure read — no `session.commit()` needed (nothing mutates).
  - [x] Response model — **type money/percentage fields as `Decimal`, not `float`** (first endpoint in this codebase to expose money/percentage figures over the wire; verified against this repo's installed `pydantic` 2.13.4: `Decimal` fields serialize to JSON as strings by default — e.g. `Decimal('12.34')` -> `"12.34"`, no float round-trip — so no manual `str(...)` conversion or custom field typing is needed; just declare the field as `Decimal`/`Decimal | None` and let Pydantic's default behavior handle it, which also keeps FastAPI's response validation on these fields instead of throwing it away by pre-stringifying):
    ```python
    class TeamPerformanceResponse(BaseModel):
        team_name: str
        achievement_pct: Decimal

    class DashboardSummaryResponse(BaseModel):
        today_sales: Decimal
        ytd_sales: Decimal
        mtd_sales: Decimal
        achievement_pct: Decimal | None
        growth_pct: Decimal | None
        team_performance: list[TeamPerformanceResponse]
        data_as_of: datetime | None  # UTC ISO 8601 — Pydantic serializes datetime correctly by default too
        is_stale: bool
    ```
    Build the response directly from the `DashboardSummary` dataclass's fields (no manual per-field string conversion needed). Pydantic still emits each `Decimal` field as a JSON string (e.g. `"12000000.00"`), so the frontend receives them as `string` via `response.json()` — `web/src/utils/format.ts` (Task 5) is typed and written accordingly (`formatCrBdt(amount: string)`, etc.), no change needed there from this fix. Do **not** add a `notification_status` field — AC #5's "No sends yet" state is static copy the frontend renders unconditionally in this story (Task 5); inventing a backend shape for it now means guessing at a contract Epic 4 (Story 4.1/4.2) will actually define when real send outcomes exist to report.
  - [x] Register in `api/main.py`: `from api.dashboard.routes import router as dashboard_router` + `app.include_router(dashboard_router)`, alongside the existing `health_router`/`auth_router` includes.

- [x] Task 4: Proxy/routing wiring so `/dashboard/summary` reaches the API in every environment (AC: #1)
  - [x] `docker/nginx/nginx.conf` — add a new `location /dashboard/ { proxy_pass http://api:8000; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }` block, placed alongside the existing `/auth/` block (before the catch-all `location /`). Without this, a production/staging browser hitting `GET /dashboard/summary` falls through to the SPA catch-all (`try_files ... /index.html`) and gets back HTML instead of JSON — this is the exact class of "deployment failure invisible until staging" bug the Architecture spine's file-structure guardrails exist to prevent.
  - [x] `web/vite.config.ts` — add `'/dashboard': 'http://localhost:8000'` to the existing `server.proxy` map (same reasoning as the current `'/auth'` entry: keeps the httpOnly session cookie same-origin in local dev too).

- [x] Task 5: Frontend `DashboardPage` (AC: #1, #2, #3, #4, #5)
  - [x] **Replace `web/src/pages/HomePage.tsx` with `web/src/pages/DashboardPage.tsx`.** `HomePage.tsx`'s own header comment already states it is a placeholder for this exact story ("Epic 2 (Story 2.2) builds the real Dashboard... This exists only to prove the session/route-guard works"). Delete `HomePage.tsx` and `HomePage.test.tsx` outright rather than leaving a dead placeholder file alongside the real page.
  - [x] Carry forward from `HomePage.tsx` (still true, nothing in this story changes it): the `GET /auth/me` session-guard effect (redirect to `/` on 401/network failure), the Logout button + `ThemeToggle`, and the account-deactivated message relay. These remain **provisional placements** at the top of the page content, exactly as `HomePage.tsx`'s comment already flagged — this story does not build the sidebar/nav shell shown in `mockups/dashboard.html` (no epics.md story owns that yet; building it here would be scope creep beyond this story's ACs, which say nothing about navigation).
  - [x] Route: `web/src/router.tsx` — replace `{ path: '/home', element: <HomePage /> }` with `{ path: '/dashboard', element: <DashboardPage /> }` (drop the `HomePage` import, add `DashboardPage`).
  - [x] Post-login/-bootstrap redirect targets: `web/src/pages/LoginPage.tsx:110` and `web/src/pages/BootstrapForm.tsx:42` both currently `navigate('/home')` — change both to `navigate('/dashboard')`. Their own test files (`LoginPage.test.tsx`, `BootstrapForm.test.tsx`) each stand up a throwaway `{ path: '/home', element: <div>...</div> }` route purely to assert the redirect landed — update those two literal `/home` strings to `/dashboard` too (both the route path and the assertion), or the tests will pass against a route that no longer exists in the real router.
  - [x] Page structure — a CSS Grid of `StatTile`s (`repeat(4, 1fr)` at `md`+, single column below `md` per AC #4 — MUI `sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(4, 1fr)' }, gap: 2 }}`, matching `mockups/dashboard.html`'s `.grid`/breakpoint intent) containing, in order: Today's Sales, YTD Sales, MTD Sales, Achievement %, Growth % (with an up/down trend indicator per `StatTile`'s existing `trend` prop — direction derived from `growth_pct >= 0`), Notification Status (static — see below), and a Team Performance tile spanning two columns listing each `team_performance` entry as a `label`/`value` row. All seven render together or not at all (AC #2) — never five tiles now and two later.
  - [x] **`StatusBadge` needs a fourth, neutral status.** `StatusBadge.tsx` today only supports `'success' | 'warning' | 'error'` (all MUI Chip semantic colors) — none of which fit "nothing has happened yet" (Notification Status placeholder) or a normal, on-time freshness reading (neither state is a success or a problem). Extend `StatusBadgeProps.status` to `'success' | 'warning' | 'error' | 'neutral'`, mapping `'neutral'` to MUI Chip's `color="default"` (its built-in grey, no new hex value invented — DESIGN.md defines no separate neutral color token, so reuse MUI's own default rather than fabricating one). This is additive, same pattern as `StatTile`'s new `loading` prop — existing call sites and `StatusBadge.test.tsx`'s current cases are unaffected; add one new test case for `status="neutral"` rendering `MuiChip-colorDefault`.
  - [x] Notification Status tile: `StatusBadge status="neutral"` with an icon that reads as "nothing yet" (not alarming) and label `"No sends yet"` — no fetch, no wiring to any backend field (per Task 3's note, there is no `notification_status` field in the response to consume).
  - [x] Freshness badge (AC #3): render unconditionally (mirrors `mockups/dashboard.html`'s always-visible freshness pill) using `StatusBadge`. Convert `data_as_of` (UTC ISO string from the API) to Asia/Dhaka `HH:MM` client-side via `Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Dhaka', hour: '2-digit', minute: '2-digit', hour12: false })` — **do not** do this conversion in the backend response; Consistency Conventions name "Dashboard" explicitly as a presentation edge where UTC-to-Asia/Dhaka conversion belongs. No new npm dependency (native `Intl`, not `date-fns-tz`/`moment`). States: fresh (`is_stale === false`) → `status="neutral"`, clock icon, `"Data as of {HH:MM}, Asia/Dhaka"`; stale (`is_stale === true`) → `status="warning"`, warning-triangle icon, `"Data as of {HH:MM} — source refresh delayed"` (matching `mockups/dashboard.html`'s exact stale-state wording); `data_as_of === null` (no import has ever succeeded) → `status="warning"`, `"No data yet"`.
  - [x] Loading state (AC #2): extend `StatTile` (`web/src/components/StatTile.tsx`) with an optional `loading?: boolean` prop — when true, render an MUI `<Skeleton variant="rounded">` in place of the `value`/`trend` content, same `Paper` shell (so tile dimensions don't jump between loading and loaded). Reuse this one component for all seven tiles' loading state rather than building a separate skeleton component. `DashboardPage` fetches on mount (`apiFetch('/dashboard/summary')`, same helper `HomePage.tsx` already used); while the request is in flight, all seven tiles render with `loading`.
  - [x] Money/percentage formatting: add `web/src/utils/format.ts` with `formatCrBdt(amount: string): string` (parse the API's string `Decimal`, divide by `1e7`, one decimal place, e.g. `"12000000.00"` -> `"1.2 Cr"`) and `formatPercent(pct: string): string` (round to nearest whole percent, e.g. `"45.00"` -> `"45%"`, matching `sample-whatsapp-report.md`'s whole-number convention). This is a genuinely shared utility, not premature abstraction: Epic 4's Daily Report generation (Story 4.2) formats the exact same figures in the exact same "Cr BDT"/whole-percent style and epics.md requires the Dashboard and Daily Report "never disagree" (Story 2.3's framing) — put the formatting logic in one place now rather than duplicating it when Story 4.2 needs it.

- [x] Task 6: Config (AC: #3)
  - [x] `config.py` — add to `Settings`:
    ```python
    # [ASSUMPTION] Neither the PRD nor epics.md define the Dashboard's exact
    # "expected refresh window" (EXPERIENCE.md names the concept but not a
    # number). The nightly import runs once per day (Story 2.1); 24 hours is
    # this story's own placeholder — generous enough that a nightly job
    # running a little late doesn't flap the badge, tight enough that a
    # genuinely missed night is caught the next morning. Same
    # provisional-default treatment as source_system_import_dir/
    # nightly_import_cron_hour above — not a hard business-sign-off blocker
    # like AC #6's aggregation formula, just flagged for the record.
    dashboard_stale_after_hours: int = Field(default=24, gt=0)
    ```

- [x] Task 7: Tests (AC: #1, #2, #3, #4, #5, #6)
  - [x] `tests/domain/test_dashboard_metrics_service.py` — new file, hand-written `Fake*Repository` classes (no mocking library, per this repo's established convention). Cases:
    - Today/MTD/YTD sums are correct at a mid-month date and correctly widen at a year/month boundary (e.g. `today = date(2026, 1, 1)`: `month_start == year_start == today`, so MTD/YTD/Today's-Sales all equal the same single day's sum — don't let an off-by-one in the boundary math silently pass because the three numbers happen to differ on other test dates).
    - `latest_per_team` results map to `team_performance` with the correct `team_name` looked up from `teams.list_all()`, sorted by name.
    - A team present in `teams.list_all()` but with zero `sales_data` rows does **not** appear in `team_performance` (not a fabricated 0% row).
    - `_aggregate_company_wide`: weighted correctly across teams of different `sales_amount`; empty `latest_per_team()` list -> `(None, None)`; all-zero `sales_amount` rows -> `(None, None)` (no `ZeroDivisionError`).
    - `is_stale` is `True` when `now - data_as_of > stale_after`, `False` at/just-under the threshold, and `True` with `data_as_of is None`.
    - Zero sales data anywhere (fresh DB) -> all sums `Decimal(0)`, `team_performance == []`, `achievement_pct`/`growth_pct` both `None`, no exception.
  - [x] `tests/adapters/persistence/test_sales_data_repository.py` — extend with real-Postgres cases for `sum_amount_in_range` (inclusive boundaries; a date just outside the range excluded; empty range returns `Decimal(0)`, not `None`) and `latest_per_team` (a team with 3 historical rows returns only its most-recent-dated row; a team with zero rows is absent from the result).
  - [x] `tests/adapters/persistence/test_team_repository.py` — extend with a `list_all` case (multiple teams, ordered by name).
  - [x] `tests/adapters/persistence/test_import_run_repository.py` — extend with a `get_last_successful_completed_at` case: only `succeeded` runs count (a `failed` run with a later `completed_at` must not be returned), `None` when no run ever succeeded.
  - [x] `tests/api/test_dashboard_routes.py` — new file, following `tests/api/test_auth_routes.py`'s `client`/`seed_user` fixture conventions: `GET /dashboard/summary` without a session -> 401 (`unauthorized` envelope, same as every other portal route); with a seeded Administrator session and seeded `sales_data`/`teams`/`import_runs` rows -> 200 with the expected shape (spot-check that Decimal fields arrive as JSON strings, not numbers, per Task 3's serialization rule).
  - [x] `tests/conftest.py`'s `_clean_tables` fixture already covers `sales_data`/`teams`/`import_runs` (added in Story 2.1) — no change needed here.
  - [x] `web/src/components/StatTile.test.tsx` — extend with a `loading` case: `loading` renders a skeleton (query by MUI's `.MuiSkeleton-root` class, mirroring `ResponsiveDataTable.test.tsx`'s class-based assertions) and not the `value`/`trend` content.
  - [x] `web/src/components/StatusBadge.test.tsx` — extend with a `status="neutral"` case asserting `MuiChip-colorDefault`, alongside the existing success/warning/error cases (unaffected, additive change).
  - [x] `web/src/pages/DashboardPage.test.tsx` — new file, following `HomePage.test.tsx`'s `vi.stubGlobal('fetch', ...)` + `createMemoryRouter` pattern. Cases: unauthenticated (`/auth/me` 401) redirects to `/`; authenticated + `/dashboard/summary` pending shows 7 skeleton tiles; authenticated + resolved response renders all seven fields' values; `is_stale: true` renders the warning-styled freshness badge with the "source refresh delayed" copy; `is_stale: false` renders the neutral freshness badge; Notification Status tile always shows "No sends yet" regardless of the mocked response (there's no field driving it).
  - [x] `uv run lint-imports` after this story's changes — confirm `ports/sales_data.py`/`ports/teams.py`/`ports/import_runs.py` stay `domain`-free and `domain/metrics.py` only imports from `ports/`.

### Review Findings

- [x] [Review][Patch] No error-state handling in `DashboardPage`'s summary fetch — if `GET /dashboard/summary` fails (non-2xx response or network error), the fetch's not-ok/`.catch` branch is silently swallowed and all seven tiles remain on loading skeletons indefinitely with no user-facing error message or retry path. Fixed: added a `summaryError` state, an MUI `Alert` error banner with a Retry button (following the existing `LoginPage`/`BootstrapForm` error-banner convention), and a `retryCount` dependency that re-triggers the fetch. [web/src/pages/DashboardPage.tsx:116-126]
- [x] [Review][Patch] Vite dev-server proxy for `/dashboard` collides with the frontend's own `/dashboard` page route — Vite's proxy matches by path prefix (`req.url.startsWith('/dashboard')`), so a direct navigation or browser refresh at `http://localhost:5173/dashboard` in local dev is forwarded to the backend (which has no bare `/dashboard` route, only `/dashboard/summary`) instead of serving the SPA, returning a 404. Production nginx avoids this because its `location /dashboard/` prefix requires the literal trailing slash the bare page path lacks — the dev proxy config wasn't given the same treatment. Fixed: scoped the proxy key to `/dashboard/summary`. [web/vite.config.ts:14]
- [x] [Review][Patch] Freshness/"Data as of" badge is not rendered at all during the initial data-loading phase (`freshness = loading ? null : freshnessBadge(...)`), contradicting the spec's explicit instruction that the badge should "render unconditionally" / be an "always-visible pill" (Task 5, AC #3). Fixed: the badge now always renders, showing a neutral "Loading…" state before the summary resolves. [web/src/pages/DashboardPage.tsx:165,179]
- [x] [Review][Patch] `DashboardPage.tsx` carries forward the Logout button, `ThemeToggle` (dark-mode PATCH + revert-on-network-failure + reset-on-logout), and the account-deactivated message relay verbatim from the deleted `HomePage.tsx`, but `DashboardPage.test.tsx` does not port any of `HomePage.test.tsx`'s corresponding test cases — this still-shipped functionality now has zero test coverage. Fixed: ported the logout, theme-toggle (PATCH/revert/reset-on-logout), and account-deactivated-relay test cases into `DashboardPage.test.tsx`. [web/src/pages/DashboardPage.test.tsx]
- [x] [Review][Patch] Growth % trend arrow/color is derived from the raw unrounded `growth_pct` value while the adjacent label uses the rounded value — e.g. `growth_pct = "-0.4"` displays a rounded "0%" label but still renders the red "down" arrow/error-styled badge, an internally inconsistent UI state. Fixed: direction is now derived from the same rounded value as the label. [web/src/pages/DashboardPage.tsx:218-219]
- [x] [Review][Patch] `_aggregate_company_wide` is typed `rows: list[Any]` instead of the spec's pseudocode signature `list[SalesData]`, losing static type-checking on `row.sales_amount`/`row.achievement_pct`/`row.growth_pct` attribute access; `domain/metrics.py` never imports `SalesData` even though it's freely importable within `domain/` (AD-1 only restricts `ports/`). Fixed: imported and typed as `list[SalesData]`. [domain/metrics.py:40]
- [x] [Review][Patch] No frontend test exercises the documented "fresh company DB" states — `achievement_pct`/`growth_pct: null` (should render "—" via `displayPercent`) or an empty `team_performance` array — even though both are real, spec-documented day-one states. Fixed: added both test cases. [web/src/pages/DashboardPage.test.tsx]
- [x] [Review][Patch] `web/src/utils/format.ts`'s `formatCrBdt`/`formatPercent` have no test coverage for negative inputs, even though `growth_pct` is explicitly documented (ingestion validator) as legitimately negative ("growth can decline"). Fixed: added `web/src/utils/format.test.ts` with negative-value cases. [web/src/utils/format.ts]

## Dev Notes

- **This story's central scope boundary: the seven-field Dashboard scaffold only.** Brand Performance (Story 2.3) and Doctor visit list (Story 2.4, Daily-Report-only, no portal screen ever) are explicitly *not* built here even though `mockups/dashboard.html` shows a Brand Performance section on the same screen — epics.md's own AC split (Story 2.3 AC: "the Dashboard's Brand Performance section... appears as an additional section beyond the seven core fields") confirms Story 2.3 extends this story's page, not the reverse. Don't pre-build Brand Performance data-wiring "since the mock shows it here" — that's exactly the kind of scope creep this workflow exists to prevent.
- **The Achievement %/Growth % "formula" question has two halves, and NEITHER is actually stakeholder-confirmed — don't be misled by Story 2.1 already having shipped.** Story 2.1 implemented `SalesData.achievement_pct`/`growth_pct` as ingested-as-given from the Source System (see `2-1-nightly-sales-reference-data-ingestion.md`'s Dev Notes), but flagged that choice itself as `[ASSUMPTION — CONFIRM]` — an engineering decision, not a business sign-off. `ARCHITECTURE-SPINE.md`'s Deferred section still lists the exact formula as an open finance/business decision. This story cannot undo Story 2.1 (out of scope, already shipped, other code depends on the current schema) — build on it as-is — but do not describe it as "resolved" or "closed" anywhere in code comments or PR descriptions; it's an existing load-bearing assumption still awaiting sign-off, same as this story's own new assumption below. This story adds a second, genuinely new open question on top: the *company-wide aggregation across teams* for the two headline tiles — `sample-whatsapp-report.md`'s own figures prove this isn't a naive average (Team A/B/C = 45/50/40 vs. headline MTD Achievement = 40 — a plain average would be 45). Task 2's `_aggregate_company_wide` implements a defensible weighted-average placeholder, isolated in its own function specifically so it's a one-function swap once confirmed. Per epics.md AC #6, this story is not "done" until a finance/business stakeholder has signed off on *both* the ingestion treatment and the aggregation — surface this prominently to whoever picks up the story, it is not merely a code comment to skim past.
- **No new Alembic migration.** This story is pure read-path: new repository read methods over tables Story 2.1 already created, one new domain module, one new route, one new frontend page. If you find yourself writing a migration for this story, stop — you've likely misread a task as requiring a schema change it doesn't.
- **Timezone handling, precisely:** `today` (the Asia/Dhaka operational day used for MTD/YTD date-range math) is computed once, server-side, in `api/dashboard/routes.py` using stdlib `zoneinfo` — this is a business-logic concern (which calendar day "today" means), not a display concern, so it belongs server-side per Consistency Conventions. In contrast, formatting `data_as_of` as `HH:MM` Asia/Dhaka *for display* is explicitly named a presentation-edge concern in the same Consistency Conventions table ("conversion to Asia/Dhaka happens only at presentation edges (WhatsApp text, **Dashboard**, ...)") — so that specific conversion happens client-side, not in the API response. Don't collapse these into "just convert to Dhaka once, server-side" — they're two different concerns that happen to both mention Asia/Dhaka.
- **Decimal-over-JSON is a new precedent this story sets.** No prior story has exposed a `Decimal` (money or percentage) through the API — Story 2.1 was backend-only. Typing response fields as `Decimal`/`Decimal | None` directly (not `float`, not manually-`str`-ed) is the choice made here — Pydantic v2 already serializes `Decimal` to a JSON string by default, so this is both the precision-safe *and* the least-code option. If a later story (e.g. Story 2.3's Brand Performance `sales`/`growth_pct` fields) needs the same figures over the wire, follow this same `Decimal`-typed-field precedent rather than introducing `float` or manual string conversion.
- **`StatTile`'s `loading` prop and `StatusBadge`'s `neutral` status are both additive extensions, not rewrites** — `StatTile.tsx`'s existing `label`/`value`/`trend` props and all four existing `StatTile.test.tsx` cases, and `StatusBadge.tsx`'s existing `success`/`warning`/`error` cases, must keep passing unchanged.
- **Why `/dashboard/summary`, not bare `/dashboard`:** the frontend's own page route is `/dashboard` (Task 5). Nginx/Vite can only proxy-vs-serve-SPA by path prefix; a bare `GET /dashboard` API resource would collide with a browser's direct navigation to the `/dashboard` page in a way `/summary`-suffixed doesn't. This mirrors why `/auth/` (not bare `/auth`) is already the API's prefix pattern.

### Project Structure Notes

- New backend files: `domain/metrics.py`; `api/dashboard/__init__.py`, `api/dashboard/routes.py`; `tests/domain/test_dashboard_metrics_service.py`; `tests/api/test_dashboard_routes.py`.
- Modified backend files: `ports/sales_data.py`, `ports/teams.py`, `ports/import_runs.py` (new read methods); `adapters/persistence/sales_data.py`, `adapters/persistence/teams.py`, `adapters/persistence/import_runs.py` (implementations); `api/main.py` (router registration); `config.py` (`dashboard_stale_after_hours`); `docker/nginx/nginx.conf` (`/dashboard/` location block); `tests/adapters/persistence/test_sales_data_repository.py`, `test_team_repository.py`, `test_import_run_repository.py` (extended).
- New frontend files: `web/src/pages/DashboardPage.tsx`, `web/src/pages/DashboardPage.test.tsx`; `web/src/utils/format.ts`.
- Modified frontend files: `web/src/router.tsx` (`/home` -> `/dashboard`); `web/src/pages/LoginPage.tsx`, `web/src/pages/BootstrapForm.tsx` (redirect target) and their two test files (throwaway `/home` route -> `/dashboard`); `web/src/components/StatTile.tsx`, `StatTile.test.tsx` (`loading` prop); `web/src/components/StatusBadge.tsx`, `StatusBadge.test.tsx` (`neutral` status); `web/vite.config.ts` (`/dashboard` proxy entry).
- Deleted frontend files: `web/src/pages/HomePage.tsx`, `web/src/pages/HomePage.test.tsx` (superseded by `DashboardPage`, exactly as `HomePage.tsx`'s own header comment anticipated).
- Fully additive to `domain/`, `ports/`, `adapters/persistence/`, `api/` — one new `api/dashboard/` package, mirroring the existing `api/auth/` package shape. First story to touch `web/src/pages/` beyond auth screens and the first to add a `web/src/utils/` directory.

### Previous Story Intelligence (from 2-1-nightly-sales-reference-data-ingestion)

- Ports stay `Any`- or primitive-typed with concrete adapter implementations narrowing the return type (e.g. `ports/users.py`'s `get_by_username(...) -> Any` vs. `adapters/persistence/users.py`'s override returning `User | None`) — Task 1's new read methods follow the same split.
- `adapters/persistence` modules import `domain.models` freely (e.g. `import_runs.py`'s `from domain.models import ImportRunStatus`); only `ports/` and `domain/` are import-linter-restricted from each other in that direction. Don't over-apply the `ports` restriction to `adapters/`.
- Postgres `DISTINCT ON` / window-function idioms are already the established way to do "latest row per group" in this codebase's adapter layer style (see Story 2.1's staging/upsert dedup logic) — Task 1's `latest_per_team` follows the same idiom rather than a Python-side loop.
- Story 2.1 flagged two `[ASSUMPTION — CONFIRM]` items (ingestion mechanism, cron trigger time) using an in-code comment plus Dev Notes cross-reference, and implemented anyway rather than blocking — Task 2/6 here follow the identical posture for the aggregation formula and staleness window respectively, distinguishing AC #6's stronger "not marked done without sign-off" language (a real blocker on completion) from the softer staleness-window assumption (an engineering call, flagged for the record but not blocking).
- Story 2.1 is genuinely this story's only upstream dependency (`SalesData`/`Team`/`ImportRun` tables, and the decision that `achievement_pct`/`growth_pct` are ingested-as-given) — re-read its Dev Notes in full before starting Task 2, not just this story's excerpt above.

### Git Intelligence

- `HEAD` is `b8fb965` ("Story 2.1: nightly sales & reference data ingestion"), working tree clean.
- Migration chain is unchanged by this story (still ends at Story 2.1's `e054c35b938f` revision) — confirms Task 1's "no new Alembic migration" call.
- Commit style: one commit per logical unit of work, imperative summary line, ending with the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2: Dashboard Summary View] (all 6 ACs, verbatim basis for this story's AC list)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3: Brand Performance Analytics] (AC establishing Brand Performance is a Dashboard *extension*, not this story's job)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#FR-3] (seven-field Dashboard definition, 3s/SM-2 budget, SM-C2 counter-metric on field-dropping)
- [Source: _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md#§13 Open Question #3, §14 Assumptions Index] (Achievement %/Growth % formula unconfirmed)
- [Source: _bmad-output/specs/spec-growthtrack/sample-whatsapp-report.md] (the figures proving company-wide Achievement % isn't a naive average of the team breakdown)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Capability → Architecture Map] (CAP-2: `api/dashboard`, `domain/metrics`)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-1] (dependency direction; read-only repository calls from the API layer are not a mutation, so they don't require a domain-service indirection layer the way writes do — still routed through `domain/metrics.py` here because the aggregation logic itself is genuinely worth unit-testing in isolation)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-6] ("Data as of HH:MM" badge reads the last-successful-import timestamp)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Consistency Conventions] (ISO 8601 UTC storage/transmission; Asia/Dhaka conversion only at presentation edges, Dashboard named explicitly; Cr BDT formatting is presentation-edge-only)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/mockups/dashboard.html] (tile layout, freshness-pill wording in both fresh and stale states, team-performance row shape)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#State Patterns] (Loading/skeleton — all seven fields together; Stale badge)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md#Responsive] (stat tiles reflow multi-column -> single-column, order not presence)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/DESIGN.md#Components] (`stat-tile`/`stat-display` token usage, status-badge "never color alone")
- [Source: domain/models.py] (`SalesData`/`Team`/`ImportRun` dataclasses — no changes needed, read-only consumption)
- [Source: ports/sales_data.py], [ports/teams.py], [ports/import_runs.py] (existing write-only method shapes this story extends)
- [Source: adapters/persistence/sales_data.py], [adapters/persistence/teams.py], [adapters/persistence/import_runs.py] (existing model/repository shape, `on_conflict_do_update` precedent not needed here since these are pure reads)
- [Source: api/auth/routes.py], [api/auth/dependencies.py] (route/package structure, `get_current_user` shared dependency precedent)
- [Source: api/main.py] (router-registration pattern)
- [Source: docker/nginx/nginx.conf], [web/vite.config.ts] (existing `/auth/`-prefix proxy pattern this story's `/dashboard/` block mirrors)
- [Source: web/src/pages/HomePage.tsx] (explicitly self-flagged as this story's placeholder; session-guard effect, Logout/ThemeToggle provisional placement carried forward verbatim)
- [Source: web/src/pages/LoginPage.tsx], [web/src/pages/BootstrapForm.tsx] (`navigate('/home')` call sites to update)
- [Source: web/src/router.tsx] (route table to update)
- [Source: web/src/components/StatTile.tsx], [StatusBadge.tsx] (existing reusable components — extend, do not replace or duplicate)
- [Source: web/src/theme/tokens.ts] (`statDisplay` typography token already wired into `StatTile`, no change needed)
- [Source: web/src/components/ResponsiveDataTable.test.tsx] (MUI-class-based assertion technique reused for `StatTile`'s new skeleton test)
- [Source: web/src/api/authClient.ts] (`apiFetch` helper reused as-is for the new `/dashboard/summary` call)
- [Source: config.py] (`Settings` field/`[ASSUMPTION]`-comment conventions for `dashboard_stale_after_hours`)
- [Source: tests/conftest.py] (`_clean_tables` already covers this story's tables from Story 2.1; `client`/`seed_user` fixtures reused for the new route test)
- [Source: tests/api/test_auth_routes.py] (API route test conventions this story's `test_dashboard_routes.py` follows)
- [Source: tests/domain/test_ingestion_service.py] (hand-written `Fake*Repository` convention, no mocking library)
- [Source: _bmad-output/implementation-artifacts/2-1-nightly-sales-reference-data-ingestion.md#Dev Notes] (the ingestion-as-given decision this story's Achievement %/Growth % framing builds directly on)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

- `uv run ruff check .` — clean after fixing 7 line-length findings introduced by this story's own new code (`adapters/persistence/teams.py`, `domain/metrics.py`, `ports/sales_data.py`, `tests/domain/test_dashboard_metrics_service.py`).
- `uv run mypy .` — 8 pre-existing errors remain (all in files this story never touches: `tests/domain/test_password_reset_service.py`, `test_bootstrap_service.py`, `test_auth_service.py`, `tests/api/test_auth_routes.py`; confirmed via `git stash` against `main` before starting). No new errors from this story's changes.
- `uv run lint-imports` — 2 contracts kept, 0 broken (AD-1: `domain` depends only on `ports`; `ports` stays framework/adapter-free).
- `uv run pytest -q` against a real `postgres:18.4-alpine` container (`gt-test-postgres`, host port 15432, per `.env` — same local dev-environment convention as Stories 1.1/1.4/2.1's Dev Agent Records) after `uv run alembic upgrade head` — 173 passed, 1 pre-existing warning, 0 failures.
- `npm test` (Vitest) — 61 passed, 12 files. One self-inflicted flake fixed during this story: the first "renders all seven fields" assertion awaited a label that renders during the loading state too, so it raced the `/dashboard/summary` fetch — switched to awaiting a value that only appears post-resolve.
- `npm run typecheck` (`tsc -b`) — clean after fixing one MUI `Stack` prop-shape error (`justifyContent` must go inside `sx`, not as a direct prop, on this repo's installed MUI version) in the new `DashboardPage.tsx`.
- `npm run lint` (eslint) — 1 pre-existing error in `LoginPage.tsx:36` (`react-hooks/set-state-in-effect`), confirmed via `git stash` to exist on `main` before this story's one-line redirect-target change to that file.
- `docker run --rm nginx:alpine nginx -t` against the updated `docker/nginx/nginx.conf` — syntax OK, test successful.

### Completion Notes List

- Implemented all 7 tasks: read-side repository ports/adapters (Task 1), `DashboardMetricsService` (Task 2), `GET /dashboard/summary` route (Task 3), Nginx/Vite proxy wiring (Task 4), `DashboardPage` frontend (Task 5), `dashboard_stale_after_hours` config (Task 6), and the full test suite (Task 7).
- All 6 ACs implemented, including AC #6's flagged `_aggregate_company_wide` placeholder — isolated in its own pure function with an in-code `[ASSUMPTION — CONFIRM]` docstring, per the story's explicit instruction.
- **AC #6 sign-off is still outstanding** — per the story's own Dev Notes, this story is implemented but **should not be considered fully "done"** until a finance/business stakeholder confirms both (a) Story 2.1's ingested-as-given per-team/per-day `achievement_pct`/`growth_pct` values and (b) this story's sales-weighted-average company-wide aggregation. This is a pre-existing-flagged business sign-off blocker, not an implementation gap — moving Status to "review" here reflects "implementation complete, ready for code review," not "AC #6 stakeholder sign-off obtained."
- Existing `Fake*Repository` test doubles in `tests/domain/test_ingestion_service.py` (`FakeSalesDataRepository`, `FakeTeamRepository`, `FakeImportRunRepository`) needed new stub method implementations (`raise NotImplementedError`) to stay instantiable now that Task 1 added new abstract methods to the corresponding ports — required for that pre-existing test file to keep passing, not a scope change to Story 2.1's tests.
- Started a local `postgres:18.4-alpine` test container (`gt-test-postgres`, already present but stopped) and Docker Desktop to run the adapter/API test suite against a real database, per this repo's no-mocking-library convention for persistence tests.

### File List

**New:**
- `api/dashboard/__init__.py`
- `api/dashboard/routes.py`
- `domain/metrics.py`
- `tests/api/test_dashboard_routes.py`
- `tests/domain/test_dashboard_metrics_service.py`
- `web/src/pages/DashboardPage.tsx`
- `web/src/pages/DashboardPage.test.tsx`
- `web/src/utils/format.ts`

**Modified:**
- `ports/sales_data.py`
- `ports/teams.py`
- `ports/import_runs.py`
- `adapters/persistence/sales_data.py`
- `adapters/persistence/teams.py`
- `adapters/persistence/import_runs.py`
- `api/main.py`
- `config.py`
- `docker/nginx/nginx.conf`
- `web/vite.config.ts`
- `web/src/router.tsx`
- `web/src/pages/LoginPage.tsx`
- `web/src/pages/BootstrapForm.tsx`
- `web/src/components/StatTile.tsx`
- `web/src/components/StatusBadge.tsx`
- `tests/adapters/persistence/test_sales_data_repository.py`
- `tests/adapters/persistence/test_team_repository.py`
- `tests/adapters/persistence/test_import_run_repository.py`
- `tests/domain/test_ingestion_service.py`
- `web/src/components/StatTile.test.tsx`
- `web/src/components/StatusBadge.test.tsx`
- `web/src/pages/LoginPage.test.tsx`
- `web/src/pages/BootstrapForm.test.tsx`

**Deleted:**
- `web/src/pages/HomePage.tsx`
- `web/src/pages/HomePage.test.tsx`

## Change Log

- 2026-07-19: Implemented Story 2.2 end-to-end — read-side repository ports/adapters for date-range sums and latest-per-team/all-teams/last-successful-import lookups (Task 1); `DashboardMetricsService` with the sales-weighted-average `_aggregate_company_wide` placeholder flagged per AC #6 (Task 2); `GET /dashboard/summary` route with `Decimal`-typed response fields (Task 3); Nginx/Vite `/dashboard/` proxy wiring (Task 4); `DashboardPage` replacing the `HomePage` placeholder, with `StatTile`'s new `loading` prop and `StatusBadge`'s new `neutral` status (Task 5); `dashboard_stale_after_hours` config (Task 6); full backend/frontend test coverage (Task 7). Full backend suite (173 tests), frontend suite (61 tests), ruff, import-linter, and `tsc` all pass clean; mypy/eslint pre-existing failures unrelated to this story confirmed via `git stash`. AC #6's finance/business stakeholder sign-off remains outstanding per the story's own Dev Notes.
