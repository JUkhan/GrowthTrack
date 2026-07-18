---
baseline_commit: a4749ec
---

# Story 1.6: Design System Foundation & Shared Interaction Patterns

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Administrator,
I want the portal's shared visual language and interaction patterns established consistently,
so that every screen reads as one trustworthy instrument, not a patchwork of ad hoc UI.

## Acceptance Criteria

1. **Given** the MUI theme, **when** brand tokens are applied, **then** primary steel blue (`#154D71`), accent growth green (`#12966B`), status-warning (`#C77700`), and status-error (`#C0362C`) colors — with tuned dark-mode counterparts (`#5B9BC4`/`#34D399`/`#F2B84B`/`#F1817A`), not a naive lightness flip — override MUI defaults; every unlisted token (background, paper, divider, text-primary/secondary, action-hover, action-disabled) inherits MUI's default light/dark theme unchanged. [Source: DESIGN.md#Colors, epics.md#Story 1.6]
2. **Given** headline figures anywhere in the portal, **when** rendered, **then** they use the `stat-display`/`stat-display-sm` typography tokens (32px/22px, semi-bold, `font-variant-numeric: tabular-nums`) so currency/percentage columns align vertically. [Source: DESIGN.md#Typography]
3. **Given** buttons, inputs, stat-tiles, modals, and status badges, **when** rendered, **then** they use the shape tokens consistently (`rounded-md`/8px default, `rounded-lg`/12px for modal containers only, `rounded-full` for badges/pills only) and flat/bordered surfaces by default (1px MUI divider border, no shadow), with shadows reserved for modals, the recipient-picker popover, toasts/snackbars, and the mobile nav drawer. [Source: DESIGN.md#Shapes, DESIGN.md#Elevation & Depth]
4. **Given** a single primary action on a screen, **when** rendered, **then** it uses `button-primary`; a destructive action uses `button-danger` and is always paired with the shared Confirmation dialog naming the real consequence, never a bare "Are you sure?". [Source: DESIGN.md#Components, EXPERIENCE.md#Component Patterns]
5. **Given** a screen with zero data (no Sales Teams, recipients, history, or audit entries), **when** rendered, **then** it shows direct copy plus one primary action specific to what's missing — never a shared generic placeholder or mascot. [Source: EXPERIENCE.md#State Patterns, DESIGN.md#Do's and Don'ts]
6. **Given** the portal's theme, **when** toggled, **then** dark mode follows system preference by default, with a manual per-Administrator override persisted via the `User.theme_preference` column (Architecture spine AD-11) — the override is only known once authenticated; an unauthenticated visitor always sees system preference. [Source: EXPERIENCE.md#Responsive & Platform, ARCHITECTURE-SPINE.md#AD-11]
7. **Given** any color-token pair used for a button or status badge, in both light and dark, **when** contrast is checked, **then** it clears WCAG 2.1 AA (4.5:1 for normal-size text/icon-on-background). [Source: DESIGN.md frontmatter status note, EXPERIENCE.md#Accessibility Floor]
8. **Given** the shared data-table pattern, **when** the viewport narrows below `sm`, **then** each row converts to a stacked key-value card, with sort/filter controls moving into a top toolbar. [Source: EXPERIENCE.md#Responsive & Platform, DESIGN.md#Components (`data-table-row`)]
9. **Given** any interactive control across the portal, **when** operated via keyboard alone, **then** it is fully operable, with `aria-label`s on icon-only controls and correct focus trap/return on modal close. [Source: EXPERIENCE.md#Accessibility Floor]
10. **Given** delivery/send status anywhere in the portal, **when** shown, **then** it lives as an in-page status badge, never a toast; MUI snackbars are reserved for reversible, low-stakes confirmations only. [Source: EXPERIENCE.md#Interaction Primitives]
11. **Given** error, empty-state, or confirmation copy anywhere in the portal, **when** written, **then** it names the actual cause or consequence directly — never "Something went wrong" or "Are you sure?" — and numbers are never rounded away. [Source: EXPERIENCE.md#Voice and Tone]

## Tasks / Subtasks

- [x] Task 1: Backend — `User.theme_preference` column, port, repository, migration (AC: #6)
  - [x] `domain/models.py`: add `class ThemePreference(StrEnum): LIGHT = "light"; DARK = "dark"; SYSTEM = "system"` next to `Role`/`UserStatus`. Add `theme_preference: ThemePreference = ThemePreference.SYSTEM` to the **end** of the `User` dataclass (after `locked_until`, same "defaults must come after non-default fields" rule Story 1.5 followed).
  - [x] `ports/users.py`: add one new abstract method, mirroring Story 1.5's `lock_until`/`clear_lockout` shape (no return value, plain `UPDATE ... WHERE id`):
    ```python
    @abstractmethod
    async def update_theme_preference(self, user_id: uuid.UUID, theme_preference: str) -> None: ...
    ```
  - [x] `adapters/persistence/users.py`: `UserModel` gains `theme_preference: Mapped[str] = mapped_column(String, nullable=False, default="system")`. Update `_to_domain` to pass `theme_preference=ThemePreference(row.theme_preference)`. Implement the repository method:
    ```python
    async def update_theme_preference(self, user_id: uuid.UUID, theme_preference: str) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(theme_preference=theme_preference)
        )
        await self._session.execute(stmt)
    ```
  - [x] New Alembic revision on top of current head `8ae7e5d0d8c9` (`uv run alembic revision --autogenerate -m "user theme preference"`). **Same gotcha as Story 1.5's `failed_login_count`:** the column is `NOT NULL` on a `users` table that already has rows from every prior story's Administrator accounts — the generated `ALTER TABLE` needs `server_default="system"` added by hand (autogenerate omits DB-side defaults for a plain `String`/`Integer` column by default), or `upgrade()` fails against existing data. Reformat to this repo's double-quote/one-arg-per-line convention.
  - [x] New `domain/preferences.py` — a thin `UserPreferenceService`, required because the Architecture spine's Consistency Conventions mandate "All writes to `User`/`Team`/`RecipientList`/... go through the domain service layer — no route handler ... touches a repository directly" (AD-1). This is genuinely the whole service; do not add anything beyond what the rule requires:
    ```python
    class UserPreferenceService:
        def __init__(self, users: UserRepository) -> None:
            self._users = users

        async def update_theme_preference(
            self, user_id: uuid.UUID, theme_preference: ThemePreference
        ) -> None:
            await self._users.update_theme_preference(user_id, theme_preference.value)
    ```
  - [x] **No audit entry for a theme-preference change.** FR-12/AD-7 enumerate what's audit-logged: directory CRUD, opt-in/out changes, Daily Report schedule changes, and logins. A personal UI preference isn't in that list and carries no security or business-forensic weight (contrast with Story 1.5's `account.locked`, which is security-relevant). Do not add an audit write here — flagged explicitly so it isn't mistaken for an oversight.

- [x] Task 2: Backend — `PATCH /auth/me` endpoint + response shape (AC: #6)
  - [x] `api/auth/routes.py`: extend `UserResponse` with `theme_preference: str`, and update `login`, `me`, and `bootstrap` to return it (`theme_preference=current_user.theme_preference.value` / `user.theme_preference.value`) — the frontend needs the preference the moment a session exists, not a second round-trip.
  - [x] New request model next to `ForgotPasswordRequest`/`ResetPasswordRequest`:
    ```python
    from typing import Literal

    class UpdateThemePreferenceRequest(BaseModel):
        theme_preference: Literal["light", "dark", "system"]
    ```
  - [x] New endpoint, same authenticated pattern as `GET /auth/me`:
    ```python
    @router.patch("/me", response_model=UserResponse)
    async def update_theme_preference(
        body: UpdateThemePreferenceRequest,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ) -> UserResponse:
        users = SqlAlchemyUserRepository(session)
        service = UserPreferenceService(users)
        await service.update_theme_preference(
            current_user.id, ThemePreference(body.theme_preference)
        )
        await session.commit()
        updated = await users.get_by_id(current_user.id)
        assert updated is not None
        return UserResponse(
            id=updated.id,
            username=updated.username,
            role=updated.role.value,
            theme_preference=updated.theme_preference.value,
        )
    ```
  - [x] Imports to add: `Literal` from `typing`, `ThemePreference` from `domain.models`, `UserPreferenceService` from `domain.preferences`.
  - [x] No Nginx or `vite.config.ts` proxy change needed — `PATCH /auth/me` falls under the existing `/auth/` prefix both already proxy (confirmed: `docker/nginx/nginx.conf`'s `location /auth/` block and `vite.config.ts`'s `proxy: { '/auth': ... }` are both prefix matches, not route-specific).

- [x] Task 3: Frontend — theme tokens, palette, typography, shape (AC: #1, #2, #3, #7)
  - [x] New `web/src/theme/tokens.ts` — plain constants transcribing `DESIGN.md`'s `colors`/`typography`/`rounded` front-matter verbatim (light + dark hex values, `stat-display`/`stat-display-sm` font specs). This is the single place brand values live; `createAppTheme` (below) only reads from here.
  - [x] New `web/src/theme/createAppTheme.ts`:
    - `palette.mode`: `'light' | 'dark'` param.
    - `palette.primary` = `{ main: primary, contrastText: primary-foreground }` (light) / `{ main: primary-dark, contrastText: primary-foreground-dark }` (dark) — this is `button-primary`.
    - `palette.error` = `status-error` / `status-error-dark` pairs — this **is** `button-danger` (DESIGN.md's status-error and the "danger" concept are the same color; MUI's built-in `color="error"` button variant needs no new palette key).
    - `palette.success` = `accent` / `accent-dark` pairs (DESIGN.md: `status-success: '{colors.accent}'`) — reserved for positive-movement/opt-in-active/delivered contexts only, per DESIGN.md's "never used for primary actions or navigation" rule; do not use `success` for any button.
    - `palette.warning` = `status-warning` / `status-warning-dark` pairs.
    - **Do not let MUI auto-compute `contrastText` for `success`/`warning`** (see Task 5 — the literal white foreground fails AA for these two). Set `contrastText` explicitly per Task 5's findings.
    - `shape.borderRadius = 8` (rounded-md — the MUI-wide default for buttons/inputs/stat-tiles).
    - `components.MuiDialog.styleOverrides.paper.borderRadius = 12` (rounded-lg, dialogs only).
    - `components.MuiPaper.defaultProps = { elevation: 0 }` and `styleOverrides.root = { border: '1px solid', borderColor: theme.palette.divider }` — makes flat-bordered the default for any `Paper`-based surface without every call site opting in. Do **not** apply this override to `MuiDialog`, `MuiPopover`, `MuiSnackbar`, or the mobile drawer's `MuiDrawer` variant — those keep MUI's default elevation/shadow (DESIGN.md: "shadows are reserved for things actually floating above the page").
    - Typography variant augmentation (MUI's documented pattern for adding non-standard variants):
      ```ts
      declare module '@mui/material/styles' {
        interface TypographyVariants {
          statDisplay: React.CSSProperties
          statDisplaySm: React.CSSProperties
        }
        interface TypographyVariantsOptions {
          statDisplay?: React.CSSProperties
          statDisplaySm?: React.CSSProperties
        }
      }
      declare module '@mui/material/Typography' {
        interface TypographyPropsVariantOverrides {
          statDisplay: true
          statDisplaySm: true
        }
      }
      ```
      then `typography.statDisplay`/`statDisplaySm` set from `tokens.ts` (`fontSize`, `fontWeight: 600`, `lineHeight`, `fontVariantNumeric: 'tabular-nums'`). Consumers render `<Typography variant="statDisplay">1.2 Cr</Typography>`.
  - [x] `web/src/App.tsx`: replace the placeholder `const theme = createTheme()` (currently annotated `// App shell only — Story 1.6 applies GrowthTrack's design tokens to this theme.`) with `createAppTheme(mode)`, where `mode` comes from Task 4's `ThemeModeProvider`. `App` must render `ThemeModeProvider` as the outermost element (it needs to exist before `mode` can be computed), with a small inner component consuming the context to build the theme and render `ThemeProvider`/`CssBaseline`/`RouterProvider`.

- [x] Task 4: Frontend — dark-mode resolution + persistence (AC: #6)
  - [x] New `web/src/theme/ThemeModeContext.tsx`:
    - `useMediaQuery('(prefers-color-scheme: dark)')` (MUI's hook) for the live system preference.
    - State: `preference: 'light' | 'dark' | 'system'`, initialized `'system'`.
    - On mount, call `apiFetch('/auth/me')`; if it succeeds, read `body.theme_preference` and set `preference` from it. If it fails (unauthenticated — e.g. on Login/Bootstrap/Forgot/Reset pages), leave `preference` at `'system'` — there is no account yet to have an override, so those pages always follow system preference, matching AC #6's "unauthenticated visitor always sees system preference."
    - Derived `mode: 'light' | 'dark'` = `preference === 'system' ? (systemPrefersDark ? 'dark' : 'light') : preference`.
    - `setPreference(next)`: optimistically updates local state, then `apiFetch('/auth/me', { method: 'PATCH', body: JSON.stringify({ theme_preference: next }) })`; on a non-2xx response, revert to the previous preference (don't leave the UI showing a preference the backend rejected/didn't persist).
    - Export `useThemeMode()` hook and `ThemeModeProvider`.
  - [x] New `web/src/components/ThemeToggle.tsx`: a 3-way MUI `ToggleButtonGroup` (System / Light / Dark), calling `useThemeMode().setPreference`. Each button is icon-only (e.g. `Brightness4`/`LightMode`/`DarkMode` from `@mui/icons-material`) — give each a matching `aria-label` (AC #9).
  - [x] `web/src/pages/HomePage.tsx`: render `<ThemeToggle />` next to the existing "Log out" button. This is an **interim placement, not a nav shell** — `HomePage.tsx`'s own existing comment already flags "Story 1.6's nav shell doesn't exist yet to host [the logout button]"; that nav shell (sidebar, avatar menu) is built by Epic 2 alongside the real Dashboard (per the mockups), not invented ad hoc here. Update the file's header comment to reflect that `ThemeToggle` now lives here for the same interim reason as "Log out," rather than leaving the old comment describing only the logout button.
  - [x] `web/src/pages/HomePage.test.tsx`: add a case asserting the toggle renders and clicking "Dark" issues a `PATCH /auth/me` with `{ theme_preference: 'dark' }` (mock `fetch` the same way `LoginPage.test.tsx` does).

- [x] Task 5: Frontend — WCAG AA contrast verification (AC: #7)
  - [x] New `web/src/theme/contrast.ts`: a small, dependency-free WCAG relative-luminance/contrast-ratio utility (`hexToRgb`, `relativeLuminance`, `contrastRatio(hexA, hexB): number`) — no new npm package; this is plain arithmetic (the standard WCAG formula) and the codebase has no existing contrast-checking dependency to reuse.
  - [x] New `web/src/theme/contrast.test.ts` asserting every `DESIGN.md` button/status-badge foreground-on-background pair, light and dark, clears 4.5:1. **Two pairs, as literally specified in `DESIGN.md`, do not clear it — confirmed by hand-computation during this story's research, not a hypothetical to "go check":**
    - `accent` (`#12966B`) with white foreground (`#FFFFFF`) — light-mode `status-success` badge and any bare accent-colored text/icon on a white/paper surface — computes to **~3.75:1**, below the 4.5:1 floor. (`accent-dark`/`accent-foreground-dark` in dark mode is fine, ~8.9:1.)
    - `status-warning` (`#C77700`) with white foreground (`#FFFFFF`) — light-mode `status-warning` badge — computes to **~3.46:1**. (`status-warning-dark`/`status-warning-foreground-dark` in dark mode is fine, ~9.3:1.)
    - `primary` (~9.0:1) and `status-error` (~5.5:1) both clear AA against white in light mode; do not change those.
  - [x] **Do not silently darken `DESIGN.md`'s locked hex values to fix this** — those are the product's brand colors, a UX-owner decision, not an engineering one (same reasoning `DESIGN.md`'s own frontmatter status: "final" implies, and the same posture Story 1.5 took toward its own `[ASSUMPTION — CONFIRM]` items). Apply this **non-hex-altering** mitigation instead, and flag it in this story's Dev Notes as `[ASSUMPTION — CONFIRM WITH UX]`:
    - For the `status-success`/`status-warning` **badge** foreground specifically (light mode), reuse `DESIGN.md`'s own already-defined `accent-foreground-dark` (`#062018`) and `status-warning-foreground-dark` (`#2B1B00`) tones in place of literal white — these are existing spec'd colors (currently used only for the dark-mode badge pairing), not invented ones, and they compute to ~4.56:1 and ~4.82:1 respectively against the light-mode backgrounds. Set `palette.success.contrastText`/`palette.warning.contrastText` to these values explicitly in `createAppTheme.ts` (Task 3) — do not transcribe `DESIGN.md`'s literal `accent-foreground`/`status-warning-foreground` (`#FFFFFF`) verbatim through as `contrastText` for these two entries, that literal value is exactly what fails the ~3.75:1/~3.46:1 check above. Don't rely on MUI's own auto-computed `getContrastText` as a substitute fix either — it uses a semi-transparent `rgba(0,0,0,0.87)` dark text and a looser `contrastThreshold` heuristic (default `3`, not a precise 4.5:1 WCAG check), so its result isn't verified the way an explicit, tested hex is.
    - For `StatTile`'s trend indicator (Task 6) — bare accent-green/status-warning text+glyph directly on a white/paper tile fails the same way `status-success`/`status-warning` badges do (the ratio is symmetric regardless of which side is "background"). Render the trend indicator using the same `StatusBadge` chip treatment (colored pill + the AA-safe foreground above), not bare colored text — this is a legitimate reading of `DESIGN.md`'s own "trend indicator ... always paired with an up/down glyph" requirement, not a new visual decision.

- [x] Task 6: Frontend — shared components (AC: #3, #4, #5, #8, #9, #10, #11)
  - [x] New `web/src/components/StatusBadge.tsx`: props `{ status: 'success' | 'warning' | 'error'; icon: ReactNode; label: string }`. Renders an MUI `Chip` (or styled `Box`) with `border-radius: rounded-full`, the variant's background/foreground from `createAppTheme`'s palette (Task 5's AA-safe foreground for success/warning), and **always** both `icon` and `label` — never a color-only rendering (AC #7/#9's accessibility floor, `DESIGN.md`'s "never color alone" rule). No default icon is baked in (the specific icon — check/clock/alert-triangle/retry-arrow — varies per call site's actual state, e.g. `Delivered` vs `Retrying (attempt n of N)` vs `Failed — retries exhausted`); callers pass an icon from `@mui/icons-material`.
  - [x] New `web/src/components/StatTile.tsx`: props `{ label: string; value: ReactNode; trend?: { direction: 'up' | 'down'; label: string } }`. Flat, bordered `Paper` (inherits Task 3's `MuiPaper` default), `label` as a small caption above `value`, `value` rendered via `<Typography variant="statDisplay">`. `trend`, if present, renders via `StatusBadge`-style treatment (`direction: 'up'` → `success` colors + an up glyph; `'down'` → `error` colors + a down glyph — **not** `warning`, matching `DESIGN.md`: "accent green up / status-error down").
  - [x] New `web/src/components/EmptyState.tsx`: props `{ message: string; actionLabel: string; onAction: () => void }` — no illustration/mascot prop exists at all (AC #5/#11 — don't leave a door open to add one later). `message` is the caller's direct, specific copy (e.g. "No recipients yet."); this component does not supply any default/generic text.
  - [x] New `web/src/components/ConfirmationDialog.tsx`: props `{ open: boolean; title: string; consequence: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void; danger?: boolean }`. `rounded-lg` `Dialog` (Task 3's `MuiDialog` override); `consequence` is rendered as the dialog body — the caller supplies the real, specific consequence text (AC #11), this component has no generic "Are you sure?" fallback copy anywhere. Confirm button uses `color="error" variant="contained"` (`button-danger`) when `danger` is true, `color="primary"` otherwise. Rely on MUI `Dialog`'s built-in focus trap and return-focus-to-trigger-on-close behavior (AC #9) — do not disable `disableRestoreFocus`.
  - [x] New `web/src/components/ResponsiveDataTable.tsx` — the shared `data-table-row` pattern (AC #8), scoped narrowly: a generic, presentational shell only (columns + rows + optional sort/toolbar), **not** the concrete filter/pagination/sort-state wiring Notification History, Recipients, and Audit Log each need — those are Epic 2/3/5's job once real data models and filter requirements exist; building that now would be guessing at APIs that don't exist yet.
    ```tsx
    interface DataTableColumn<T> {
      key: string
      header: string
      render: (row: T) => ReactNode
      sortable?: boolean
    }

    interface ResponsiveDataTableProps<T> {
      columns: DataTableColumn<T>[]
      rows: T[]
      getRowKey: (row: T) => string
      sortColumn?: string
      sortDirection?: 'asc' | 'desc'
      onSortChange?: (columnKey: string) => void
      toolbar?: ReactNode
    }
    ```
    Renders `toolbar` (if provided) above the table/card block unconditionally — this alone satisfies AC #8's "sort/filter controls moving into a top toolbar" below `sm`, since it's the same DOM position at every breakpoint, only the row rendering below it changes. At `sm` and above: MUI `Table` with `hover` rows (inherits `action.hover`, no custom striping per `DESIGN.md`) and `TableSortLabel` on `sortable` columns wired to `onSortChange`. Below `sm` (`useMediaQuery(theme.breakpoints.down('sm'))`): each row renders as a bordered `Card` containing one label/value line per column (`column.header`: `column.render(row)`) — a stacked key-value card, per AC #8's literal wording.
  - [x] **Toast/snackbar guardrail (AC #10) — no new component, a documented rule.** No `Snackbar` exists anywhere in this codebase yet. When a future story adds one (e.g. Epic 3's "Recipient saved"), it must be reversible/low-stakes only; delivery/send status must always render via `StatusBadge`, never a `Snackbar`. Record this in Dev Notes below so it isn't rediscovered ad hoc per-story.
  - [x] New `web/src/testUtils/renderWithTheme.tsx`: `renderWithTheme(ui: ReactElement, mode: 'light' | 'dark' = 'light')` wrapping `render()` in `<ThemeProvider theme={createAppTheme(mode)}><CssBaseline />{ui}</ThemeProvider>` — every new component test below needs `theme.typography.statDisplay`/the palette to actually resolve, and this avoids six near-identical wrapper blocks (a genuine, immediate 6-consumer case for extraction, unlike a one-off).
  - [x] Component tests (`vitest` + RTL, using `renderWithTheme`): `StatusBadge.test.tsx` (renders icon + label together for each variant, never label-only); `StatTile.test.tsx` (renders label/value/optional trend, trend uses the badge-chip treatment not bare text); `EmptyState.test.tsx` (renders the passed message/action, calling `onAction` on click); `ConfirmationDialog.test.tsx` (renders `consequence` text verbatim, confirm button is `color="error"` only when `danger`, focus returns to a trigger button after close — use `userEvent` + a wrapper component with a real trigger button, not a bare mount); `ResponsiveDataTable.test.tsx` (renders as a `table` at default/desktop width, renders as stacked cards when `theme.breakpoints.down('sm')` matches — mock `window.matchMedia` the same way MUI's `useMediaQuery` expects, consistent with any existing `matchMedia` stub in `setupTests.ts`/test files, or add one if none exists yet).

- [x] Task 7: Verify no regression on existing auth pages (AC: #1-#3, #7, #9)
  - [x] `LoginPage.tsx`, `BootstrapForm.tsx`, `ForgotPasswordPage.tsx`, `ResetPasswordPage.tsx`, `AuthFormShell.tsx` need **no code changes** — they already render through MUI `Button`/`TextField`/`Alert`/`Link`, so `createAppTheme`'s palette/shape/typography overrides apply automatically once `App.tsx` (Task 3) switches from the placeholder `createTheme()` to `createAppTheme(mode)`. Run the existing `LoginPage.test.tsx`/`BootstrapForm.test.tsx`/`ForgotPasswordPage.test.tsx`/`ResetPasswordPage.test.tsx` suites unmodified and confirm they still pass — they query by role/label text, not by computed style, so a pure theme swap should not break them; if one does break, that's a signal the theme override reached further than intended (e.g. into `MuiPaper` defaults these pages didn't opt into), not a reason to adjust the test's queries to match.

### Review Findings

- [x] [Review][Patch] Theme preference doesn't refresh across login/logout, violating AC #6 [web/src/theme/ThemeModeContext.tsx:19-49, web/src/pages/LoginPage.tsx:103, web/src/pages/HomePage.tsx:59]
- [x] [Review][Patch] Global `MuiPaper` border override leaks onto `Dialog`/`Popover`/`Snackbar`/`Drawer`, violating AC #3 / Task 3's explicit exclusion [web/src/theme/createAppTheme.ts:62-79]
- [x] [Review][Patch] `setPreference` has no error handling for a rejected `apiFetch` call (network failure) — unhandled promise rejection, optimistic state never reverted [web/src/theme/ThemeModeContext.tsx:39-49]
- [x] [Review][Patch] Race: the mount-time `GET /auth/me` fetch can resolve after a user-initiated `setPreference` and silently overwrite it with the stale value [web/src/theme/ThemeModeContext.tsx:19-49]
- [x] [Review][Patch] `PATCH /auth/me` re-fetches the user after commit and guards with a bare `assert`, which is stripped under `-O` and produces an unhandled 500 instead of a clean error if the row is gone [api/auth/routes.py:212-214]
- [x] [Review][Patch] `StatusBadge` hardcodes `borderRadius: 9999` instead of importing `rounded.full` from `theme/tokens.ts` [web/src/components/StatusBadge.tsx:20]
- [x] [Review][Patch] `ThemeModeProvider` and `HomePage` independently fire duplicate `GET /auth/me` requests on first load of an authenticated `/home` [web/src/theme/ThemeModeContext.tsx:22, web/src/pages/HomePage.tsx:30]
- [x] [Review][Patch] `StatusBadge`'s `icon` prop is typed `ReactNode` but force-cast to `ReactElement` — a non-element value would throw at runtime; narrow the prop type instead [web/src/components/StatusBadge.tsx:6,18]
- [x] [Review][Patch] `ResponsiveDataTable`'s `TableSortLabel` receives `direction={undefined}` when `sortColumn` is set without `sortDirection` [web/src/components/ResponsiveDataTable.tsx:77]
- [x] [Review][Patch] No test exercises the login→home transition, the logout→home transition, or `setPreference`'s failure-revert path — the exact paths that would have caught the AC #6 and error-handling findings above [web/src/pages/HomePage.test.tsx]
- [x] [Review][Defer] Alembic migration sets `server_default="system"` but `UserModel.theme_preference` has no matching `server_default`, so model metadata and live schema disagree [alembic/versions/d4d9c5b96249_user_theme_preference.py:32, adapters/persistence/users.py:30] — deferred, pre-existing (same convention already used by `failed_login_count`/`locked_until`, not a regression introduced here)
- [x] [Review][Defer] `_to_domain` calls `ThemePreference(row.theme_preference)` with no guard against an unrecognized DB value, which would raise an unhandled `ValueError` [adapters/persistence/users.py:44] — deferred, pre-existing (same unguarded pattern already used for `Role(row.role)`/`UserStatus(row.status)`, not a regression introduced here)

## Dev Notes

- **Why `theme_preference` needs a domain service (`domain/preferences.py`) even though it's a one-line update.** The Architecture spine's Consistency Conventions state plainly: "All writes to `User`/... go through the domain service layer — no route handler ... touches a repository directly (AD-1)." This is a structural rule, not proportional to how much logic the write contains — Story 1.1-1.5 never broke it for a "just one field" case either. Keep `UserPreferenceService` exactly as thin as the rule requires; don't add validation/business logic it doesn't need.
- **Why theme-preference changes aren't audit-logged.** AD-7/FR-12 name the audited action set explicitly: directory CRUD, opt-in/out, Daily Report schedule changes, and logins. A personal display preference isn't a business-forensic or security-relevant action like Story 1.5's `account.locked`, so it's deliberately excluded — flagged here so a reviewer doesn't read the omission as a miss.
- **The two failing AA color pairs are a real, computed finding, not a "go verify this" placeholder.** `accent` (#12966B) and `status-warning` (#C77700) both fail 4.5:1 against white in light mode (~3.75:1 and ~3.46:1) — as *both* a badge background-with-white-text pair and as bare colored text/icon on a white surface (the ratio is symmetric). `primary` and `status-error` both clear AA comfortably (~9.0:1, ~5.5:1), as do all four dark-mode pairs. Task 5's mitigation (reuse `DESIGN.md`'s own `*-foreground-dark` tones as the light-mode badge/chip foreground, and never render accent/warning as bare text) fixes every concrete usage this story introduces without altering a single `DESIGN.md` hex value. If a later story needs accent/warning as bare inline text outside a badge/chip context, that specific case will need a fresh UX decision — don't extrapolate this fix to a context it wasn't verified for.
- `[ASSUMPTION — CONFIRM WITH UX]` **`palette.success`/`palette.warning`'s `contrastText` in `createAppTheme.ts` uses `DESIGN.md`'s own `accent-foreground-dark` (`#062018`) and `status-warning-foreground-dark` (`#2B1B00`) tones in place of the literal `accent-foreground`/`status-warning-foreground` (`#FFFFFF`) DESIGN.md specifies**, because the literal white foreground fails WCAG AA in light mode (~3.75:1/~3.46:1 — see above). This is a non-hex-altering mitigation (no `DESIGN.md` brand color was changed) but it does deviate from what `DESIGN.md`'s frontmatter literally names as each token's foreground; a UX owner should confirm this substitution is acceptable rather than, e.g., wanting a different light-mode-only foreground value introduced instead.
- **Scope boundary: no nav shell, sidebar, avatar menu, or full Settings screen in this story.** `epics.md`'s Story 1.6 ACs cover tokens, shared components, and the dark-mode *mechanism* — not the portal chrome that will host them. The mockups' sidebar/nav belongs to Epic 2 (Dashboard); the full Settings screen (Daily Report send-time + own account/password + theme, per `EXPERIENCE.md`'s IA table) is Story 4.4's job. This story's `ThemeToggle` lives on `HomePage.tsx` as an explicitly interim placement, matching the precedent `HomePage.tsx` already set for its own "Log out" button (Story 1.4).
- **Scope boundary: `ResponsiveDataTable` is a presentational shell, not a working table.** It has no built-in filter state, no pagination, no data-fetching — Notification History (Story 5.1), Recipients (Story 3.1-3.2), and Audit Log (Story 5.2) each wire real columns/sort/filter logic against real APIs on top of this shell when they're built. Building that logic speculatively now would mean guessing at API shapes that don't exist yet.
- **`palette.success` = `accent`, deliberately, not a new palette key.** `DESIGN.md` itself defines `status-success: '{colors.accent}'` — reusing MUI's built-in `success` semantic slot for the growth-green token (rather than inventing a `growth`/`accent` custom palette key) keeps every MUI component that already understands `color="success"` correctly styled for free, and matches `DESIGN.md`'s own color-token aliasing.
- **`button-danger` = MUI's built-in `color="error"`, not a new palette key either.** `DESIGN.md`'s `status-error` IS the "danger" concept — there's no need for a third, semantically-identical color slot.
- **`AuthFormShell`/`LoginPage`/`BootstrapForm`/`ForgotPasswordPage`/`ResetPasswordPage` need zero code changes** (Task 7) — this is the payoff of doing brand/shape/typography work at the theme level instead of per-page: every existing MUI-based screen picks up the new look automatically the moment `App.tsx` swaps in `createAppTheme`.
- **No `web/src/theme/tokens.ts` value should silently drift from `DESIGN.md`'s frontmatter.** If a future design change updates `DESIGN.md`'s hex values, `tokens.ts` is the one file that needs to change to match — don't duplicate the literal hex strings into `createAppTheme.ts` or component files directly.

### Project Structure Notes

- New backend files: `domain/preferences.py`, a new Alembic revision on top of `8ae7e5d0d8c9`, plus test additions (no new backend test *files* strictly required — additions to existing `tests/domain/`, `tests/adapters/persistence/test_user_repository.py`, `tests/api/test_auth_routes.py` suffice, though a dedicated `tests/domain/test_preferences_service.py` is reasonable given the new module).
- Modified backend files: `domain/models.py` (`ThemePreference`, `User.theme_preference`), `ports/users.py`, `adapters/persistence/users.py`, `api/auth/routes.py` (`UserResponse` extension, `PATCH /auth/me`).
- New frontend files: `web/src/theme/tokens.ts`, `web/src/theme/createAppTheme.ts`, `web/src/theme/ThemeModeContext.tsx`, `web/src/theme/contrast.ts` (+ `.test.ts`), `web/src/components/StatusBadge.tsx`, `StatTile.tsx`, `EmptyState.tsx`, `ConfirmationDialog.tsx`, `ResponsiveDataTable.tsx`, `ThemeToggle.tsx` (each + `.test.tsx`), `web/src/testUtils/renderWithTheme.tsx`.
- Modified frontend files: `web/src/App.tsx` (wire `createAppTheme`/`ThemeModeProvider`), `web/src/pages/HomePage.tsx` (+ `.test.tsx`, add `ThemeToggle`).
- Fully additive to the existing `domain/`, `ports/`, `adapters/persistence/`, `api/auth/`, `web/src/components/`, `web/src/pages/` structure — no new top-level directories on either side, `web/src/theme/` and `web/src/testUtils/` are new subdirectories under the existing `web/src/`.

### Previous Story Intelligence (from 1-5-login-lockout-password-reset)

- `Settings`-sourced policy values use `Field(default=..., gt=0)`; **not applicable here** — `theme_preference` has no numeric policy value, it's a plain enum-backed column, so no new `Settings` field is needed for this story.
- Migration gotcha carries forward exactly: a new `NOT NULL` column on `users` needs a hand-added `server_default` because autogenerate won't infer one from a plain SQLAlchemy `default=`.
- `AD-1`'s "route handlers never touch a repository directly" was already the working pattern in every Story 1.x route (`AuthenticationService`, `BootstrapService`, `PasswordResetService`, `SessionService`) — `UserPreferenceService` (Task 1) is the same shape for a much smaller job, not a new pattern.
- Frontend forms established `apiFetch` (relative paths, `credentials: 'include'`) as the one fetch wrapper — `ThemeModeContext.tsx`/`ThemeToggle.tsx` reuse it, no new HTTP client.
- Story 1.5 extracted `AuthFormShell` specifically to stop deferring shared-component work a third time; this story is the next logical point where shared *non-form* components (badges, tiles, dialogs, tables) get the same treatment before Epic 2-5 each reinvent their own.

### Git Intelligence

- `HEAD` is `a4749ec` ("Story 1.5: login lockout & password reset"), working tree clean.
- Migration chain so far: `3066ace65d15` (baseline) → `98ddc369b175` (`users`/`audit_log_entries`) → `a2fafc72668b` (`revoked_tokens`) → `8ae7e5d0d8c9` (`failed_login_count`/`locked_until`/`password_reset_tokens`). This story's migration is the fifth revision, built on `8ae7e5d0d8c9`.
- `web/src/App.tsx` already carries a comment placed by Story 1.0/1.1 specifically pointing at this story: `// App shell only — Story 1.6 applies GrowthTrack's design tokens to this theme.` — confirms the theme work was always intended to land here, not invented scope.
- `web/src/pages/HomePage.tsx` similarly already flags: "Story 1.6's nav shell doesn't exist yet to host [the logout button]" — corroborates this story's own scope boundary (no nav shell) rather than contradicting it; the comment describes a future nav shell (Epic 2), not a requirement that this story build one.
- Commit style: one commit per logical unit of work, imperative summary line, ending with the `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.

### Latest Technical Notes (from web research, 2026-07-18)

- MUI v9 (`@mui/material` per the Architecture spine's pinned `9.2.0`) supports custom `Typography` variants via TypeScript module augmentation exactly as shown in Task 3 — this is MUI's own documented pattern for the `stat-display`/`stat-display-sm` tokens, not a workaround.
- WCAG 2.1 AA's normal-text contrast floor is 4.5:1; the 3:1 floor only applies to "large text" (≥18pt/24px regular or ≥14pt/18.66px bold) or non-text UI components/graphical objects. Status-badge/status-warning text at the mockups' 12px/600-weight size does not qualify as "large text," so 4.5:1 is the correct floor applied throughout this story (not the looser 3:1 some component libraries default to).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.6: Design System Foundation & Shared Interaction Patterns]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/DESIGN.md] (Colors, Typography, Elevation & Depth, Shapes, Components, Do's and Don'ts — the primary source for every token value in this story)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md] (Component Patterns, State Patterns, Accessibility Floor, Interaction Primitives, Responsive & Platform, Voice and Tone)
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/mockups/dashboard.html], [mockups/notification-history.html] (concrete visual reference for stat-tile/status-badge/data-table-row sizing and hex usage — spine wins on conflict per DESIGN.md/EXPERIENCE.md's own rule)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#AD-11] ("`User` gains a `theme_preference` column (`light`/`dark`/`system`, default `system`) backing the per-Administrator dark-mode override... adapters/persistence addition... none require a new port or adapter")
- [Source: _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md#Consistency Conventions] (AD-1's "no route handler touches a repository directly" rule — basis for Task 1's `UserPreferenceService`)
- [Source: _bmad-output/implementation-artifacts/1-5-login-lockout-password-reset.md#Dev Notes] (migration `server_default` gotcha, `AuthFormShell` extraction precedent)
- [Source: web/src/App.tsx], [web/src/pages/HomePage.tsx] (existing comments pointing at this story's scope)
- [Source: domain/models.py], [ports/users.py], [adapters/persistence/users.py], [api/auth/routes.py], [api/auth/dependencies.py], [config.py], [tests/conftest.py]
- [Source: web/src/api/authClient.ts], [web/src/pages/LoginPage.tsx], [web/src/pages/HomePage.tsx], [web/src/App.tsx], [web/vite.config.ts], [docker/nginx/nginx.conf]
- WCAG 2.1 Success Criterion 1.4.3 (Contrast Minimum) — https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
- MUI Theming — Typography variants — https://mui.com/material-ui/customization/typography/#adding-amp-disabling-variants

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5 (claude-sonnet-5)

### Debug Log References

### Completion Notes List

- Task 1: Added `ThemePreference` enum + `User.theme_preference` field, `UserRepository.update_theme_preference` port method, `SqlAlchemyUserRepository` implementation, Alembic revision `d4d9c5b96249` (hand-added `server_default="system"`), and `domain/preferences.py`'s `UserPreferenceService`. New repository/domain-service tests all pass (11/11).
- Task 2: Extended `UserResponse` with `theme_preference`; `login`/`me`/`bootstrap` now return it. Added `PATCH /auth/me` with `UpdateThemePreferenceRequest`. Updated two existing exact-body assertions in `test_auth_routes.py` and added 3 new tests for the PATCH endpoint. Full `tests/api/` suite passes (46/46).
- Task 3: Added `web/src/theme/tokens.ts` (verbatim `DESIGN.md` transcription) and `createAppTheme.ts` (palette/shape/typography, `statDisplay`/`statDisplaySm` variant augmentation, flat-bordered `MuiPaper` default, `rounded-lg` `MuiDialog`). Wired `App.tsx` to `ThemeModeProvider` + `createAppTheme(mode)`.
- Task 4: Added `ThemeModeContext.tsx` (system-preference detection via `useMediaQuery`, `/auth/me` read on mount, optimistic-with-revert `PATCH` on change) and `ThemeToggle.tsx` (3-way icon-only `ToggleButtonGroup` with `aria-label`s). Wired into `HomePage.tsx` next to "Log out"; added a jsdom `matchMedia` stub to `setupTests.ts` (none existed) since `useMediaQuery` needs it. Added a `HomePage.test.tsx` case covering the toggle → `PATCH /auth/me`.
- Task 5: Added `contrast.ts` (dependency-free WCAG luminance/ratio utility) and `contrast.test.ts`, confirming the two documented AA failures (`accent`/`status-warning` vs. literal white in light mode) and that the `*-foreground-dark`-reuse mitigation clears AA. Flagged the mitigation as `[ASSUMPTION — CONFIRM WITH UX]` in Dev Notes.
- Task 6: Added `StatusBadge`, `StatTile`, `EmptyState`, `ConfirmationDialog`, `ResponsiveDataTable` (+ each `.test.tsx`) and `testUtils/renderWithTheme.tsx`. All use `renderWithTheme`; `ResponsiveDataTable.test.tsx` stubs `matchMedia` per-test for the `sm`-breakpoint stacked-card behavior.
- Task 7: Confirmed via `git diff --stat` that `LoginPage.tsx`/`BootstrapForm.tsx`/`ForgotPasswordPage.tsx`/`ResetPasswordPage.tsx`/`AuthFormShell.tsx` have zero changes; their existing test suites (21 tests) pass unmodified against the new theme.
- Typecheck (`tsc -b`) and lint (`eslint .`) both pass on all new/modified files — fixed two typecheck errors (unused `vi` import; MUI v9's `Stack` no longer accepts `alignItems` as a direct prop, moved to `sx`) and one lint error (`react-refresh/only-export-components` on the co-located `ThemeModeProvider`/`useThemeMode` — disabled inline with rationale, an intentional, story-specified single-file pattern). The one remaining lint error (`LoginPage.tsx`, `react-hooks/set-state-in-effect`) predates this story (confirmed against baseline `a4749ec` via `git stash`) and is out of this story's scope per Task 7.

### File List

- domain/models.py (modified)
- domain/preferences.py (new)
- ports/users.py (modified)
- adapters/persistence/users.py (modified)
- alembic/versions/d4d9c5b96249_user_theme_preference.py (new)
- api/auth/routes.py (modified)
- tests/adapters/persistence/test_user_repository.py (modified)
- tests/domain/test_preferences_service.py (new)
- tests/api/test_auth_routes.py (modified)
- web/src/theme/tokens.ts (new)
- web/src/theme/createAppTheme.ts (new)
- web/src/theme/ThemeModeContext.tsx (new)
- web/src/theme/contrast.ts (new)
- web/src/theme/contrast.test.ts (new)
- web/src/components/ThemeToggle.tsx (new)
- web/src/components/StatusBadge.tsx (new)
- web/src/components/StatusBadge.test.tsx (new)
- web/src/components/StatTile.tsx (new)
- web/src/components/StatTile.test.tsx (new)
- web/src/components/EmptyState.tsx (new)
- web/src/components/EmptyState.test.tsx (new)
- web/src/components/ConfirmationDialog.tsx (new)
- web/src/components/ConfirmationDialog.test.tsx (new)
- web/src/components/ResponsiveDataTable.tsx (new)
- web/src/components/ResponsiveDataTable.test.tsx (new)
- web/src/testUtils/renderWithTheme.tsx (new)
- web/src/App.tsx (modified)
- web/src/pages/HomePage.tsx (modified)
- web/src/pages/HomePage.test.tsx (modified)
- web/src/setupTests.ts (modified)

## Change Log

- 2026-07-18: Implemented Story 1.6 end-to-end — `User.theme_preference` column/service/endpoint (Tasks 1-2); MUI theme tokens, dark-mode context/toggle, WCAG AA contrast utility, and five shared components (Tasks 3-6); confirmed zero regression on existing auth pages (Task 7). Full backend (112) and frontend (57) suites pass; typecheck and lint clean aside from one pre-existing, out-of-scope `LoginPage.tsx` lint finding predating this story.
