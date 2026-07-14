---
name: GrowthTrack
status: final
sources:
  - _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md
  - _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/addendum.md
  - _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/review-edge-case-hunter.md
  - _bmad-output/specs/spec-growthtrack/SPEC.md
  - _bmad-output/specs/spec-growthtrack/entities.md
  - _bmad-output/specs/spec-growthtrack/sample-whatsapp-report.md
  - _bmad-output/specs/spec-growthtrack/stack.md
  - _bmad-output/specs/spec-growthtrack/architecture-diagrams.md
updated: 2026-07-14
---

# GrowthTrack — Experience Spine

> Phase 1: WhatsApp Sales Reporting & Admin Portal. Paired with `DESIGN.md`, which owns visual identity; this spine owns information architecture, behavior, states, and journeys. Both spines win on conflict with any mock, wireframe, or import.

## Foundation

Responsive web, React + MUI, single surface reached two ways: an **authenticated portal** (Administrator role only, per PRD §4.1/FR-1/FR-2) and an **unauthenticated WhatsApp channel** (Sales Users, Managers, Administrators alike receive the Daily Report and any Manual Notification as a plain-text WhatsApp message — they never log into anything for this). `DESIGN.md` is the visual identity reference for both; the WhatsApp side inherits its typography/tone discipline conceptually even though WhatsApp's own renderer constrains actual formatting (no rich text, no images — SPEC non-goal).

Mobile-solid by requirement: the portal must be genuinely usable on a phone browser, not just non-broken, because UJ-1's Rehana may need to send an urgent notification from the field. Dark mode is in scope from v1. Single-tenant, single Administrator role — no multi-org, no permission tiers beyond "Administrator" today (§4.1 explicitly defers broader RBAC).

## Information Architecture

`[NOTE]` Doctor Visit Prioritization (FR-5) has no dedicated portal screen — per PRD FR-3's consequence, it's Daily-Report-only, not a Dashboard or portal surface. `GET /doctors` (per `architecture-diagrams.md`) backs report generation, not an admin-facing view. The table below deliberately does not invent a Doctors screen beyond what the FRs support.

| Surface | Reached from | Purpose |
|---|---|---|
| Login | App URL, unauthenticated | Administrator authentication (FR-1). Also hosts the first-run bootstrap path (no Administrator exists yet) and password-reset. |
| Dashboard | Post-login default / nav | Live single-screen summary: Today's Sales, YTD, MTD, Achievement %, Growth %, per-team breakdown, notification status (FR-3), plus Brand Performance (FR-4). → `mockups/dashboard.html` |
| Notifications ▸ Compose | Nav / Dashboard quick action | Compose and send a Manual Notification (FR-8). → `mockups/notifications-compose.html` |
| Notifications ▸ History | Nav / Dashboard notification-status tile | Full log of scheduled and manual sends, filterable by recipient/date/type, drill-down to per-recipient delivery outcome (FR-11). → `mockups/notification-history.html` |
| Recipients | Nav | Manage Users, Recipient Groups, Recipient Channels, Sales Teams; opt-in/out state; directory CRUD (FR-9, FR-10). |
| Audit Log | Nav / cross-linked from Recipients and History | Append-only log of administrative actions — directory changes, opt-in/out toggles, schedule changes, logins (FR-12). |
| Settings | Avatar menu | Daily Report global send-time (FR-6), own account/password, theme (light/dark), logout. |
| *(WhatsApp) Daily Report* | Arrives automatically, once/day | The scheduled message every Recipient reads without touching the portal (FR-6). Not a portal surface, but part of this IA — see `sample-whatsapp-report.md` for the reference layout. |
| *(WhatsApp) Manual Notification* | Arrives on Administrator trigger | The ad-hoc message from Notifications ▸ Compose (FR-8). |

Modal stacking is one level deep everywhere (open a dialog on top of a surface, never a dialog on top of a dialog) — confirmations and the recipient picker are the only floating layers this system needs.

→ Composition reference: `mockups/dashboard.html`, `mockups/notifications-compose.html`, `mockups/notification-history.html`. Spine wins on conflict with any mock.

**Surface closure check:** every JTBD (§2.1 of the PRD) lands somewhere above — Dashboard and Notifications serve the Administrator's control-plane needs; the WhatsApp surfaces serve Sales Rep/Manager visibility without requiring portal access, consistent with §2.2's explicit non-users.

## Voice and Tone

Direct, declarative, cause-stated. This is a tool for people checking whether something serious went right or wrong — never cute, never exclamatory, never vague about why.

- Error and failure copy names the actual cause where one is known: **"Failed — invalid number"**, not "Something went wrong." When the cause truly isn't known, say that plainly instead of inventing false specificity.
- Empty states state what's missing and the one action that resolves it: **"No recipients yet. Add your first recipient."** — never a mascot, never a joke, per `DESIGN.md` Do's and Don'ts.
- Confirmation copy states the real consequence, not a generic prompt: **"This removes Dr. Rahman's territory assignment. Sales reps in Chattogram North will stop seeing this entry."** — not "Are you sure?"
- Numbers are never rounded away in copy — if the UI says "42 recipients," it means exactly 42, because this product's entire value proposition is precision over vibes (SM-1, SM-3, SM-C1).

## Component Patterns

Behavioral specs; visual specs for the same components live in `DESIGN.md` Components.

- **Status badge** (`{components.status-badge}`) — drives Dashboard notification status, Notification History rows, and Recipient opt-in state. States: `Queued` → `Sending` → `Delivered` / `Retrying (attempt n of N)` / `Failed — retries exhausted`. Each carries its own icon + label; nothing is ever inferred from color alone.
- **Recipient picker** — used by both Notifications ▸ Compose and directory group/channel/team editing. Selecting across mechanisms (an individual plus a team they already belong to) shows the de-duplicated count live: *"14 selected → 11 unique recipients (3 overlaps merged)"* — makes FR-6/FR-8's dedupe guarantee visible, not just true-but-invisible in the backend.
- **Notification composer** — Administrator picks a pre-approved WhatsApp template (per addendum: sends are billed Meta template messages, not free text) and fills the template's variable slots; a live preview renders exactly what the recipient will see on WhatsApp. Free-form body text is **not** offered beyond what the chosen template's variables allow — this is a hard constraint from the messaging platform, not a product choice, and the UI should make the constraint legible rather than pretend it's a plain textarea.
- **Data table** — shared pattern across Notification History, Recipients, and Audit Log: sortable columns, filter toolbar (recipient, date range, type — per FR-11), pagination, and row drill-down (a group/team send expands into one row per individual recipient outcome, so "did X receive Y" (UJ-3) is always answerable down to the individual).
- **Directory form** — Recipient add/edit validates phone-number uniqueness inline (not just on submit) and surfaces opt-in/consent state with its timestamp directly in the form, not hidden behind a separate tab.
- **Confirmation dialog** — single pattern for every destructive/high-stakes action (delete recipient, deactivate last Administrator guard, opt someone out, override a stale schedule): names the real consequence, requires explicit confirm, uses `{components.button-danger}` for the confirming action only.

## State Patterns

- **Empty** — zero Sales Teams, zero recipients, zero notification history, zero audit entries: each gets its own direct copy + primary action, never a shared generic "no data" placeholder.
- **Loading** — skeleton stat tiles on Dashboard load, targeting the ≤3s budget (SM-2); no field is ever dropped to hit the budget faster (SM-C2) — the skeleton fills in as data arrives — all seven fields appear, or none do yet.
- **Stale** — if the upstream Source System hasn't refreshed within its expected window, the Dashboard shows an explicit **"Data as of HH:MM"** badge rather than silently presenting old numbers as current.
- **In-progress** — sending a Manual Notification disables the send control and shows "Sending to 42 recipients…"; no double-submit is possible.
- **Failed / retrying** — always named via the status-badge pattern above; failed-with-retries-exhausted is visually and textually distinct from still-retrying.
- **Blocked** — zero recipients selected disables Send with an inline reason, not a silent no-op (FR-8); deleting/deactivating the last Administrator is blocked with an explanatory tooltip (FR-2).
- **Conflict** — editing a Recipient record that someone else just changed surfaces a conflict dialog showing both versions; it never silently overwrites.
- **Auth edge states** — login lockout after repeated failed attempts shows a cooldown timer, not a bare "try again" loop; an Administrator deactivated mid-session is logged out on their next action with a plain explanation, not a mysterious redirect; if zero Administrators exist (fresh deployment), Login routes to a one-time bootstrap flow instead of a dead end.

## Interaction Primitives

- **Navigation** — persistent left sidebar at `md` and above; collapses to a bottom nav / slide-in drawer below `md` (mobile-solid requirement).
- **Transient vs. persistent feedback** — MUI snackbars are used only for reversible, low-stakes confirmations ("Recipient saved"). Anything about delivery or send status lives as an in-page status badge, never a toast — a toast disappears, and this product's premise is that nothing important is allowed to disappear.
- **Confirm-before-destroy** — every destructive action requires the named-consequence confirmation dialog described above; there is no bare "Delete" button anywhere that acts immediately.
- **Forms** — standard tab order, Enter-to-submit on single-line forms, inline validation on blur (phone uniqueness, required fields) rather than only on submit.
- **Keyboard** — full keyboard operability is required (accessibility floor below); no bespoke shortcut layer is introduced beyond that. `[ASSUMPTION: this tool is opened a handful of times a day, not lived in, so a command-palette-style shortcut system would be over-engineering.]`

## Accessibility Floor

`[ASSUMPTION: WCAG 2.1 AA taken as the floor — not stated in the PRD, but "consumer-grade" stakes plus Bangladesh PDPA-adjacent data governance both argue for treating this as real, not best-effort.]`

- Status is never color-only anywhere in the system — every badge, trend arrow, and table status cell pairs color with an icon and a text label (see `DESIGN.md` Colors/Components).
- Every interactive control (directory forms, notification composer, table filters, recipient picker) is fully keyboard-operable; icon-only controls carry an `aria-label` matching their visible text equivalent.
- Modals trap and correctly return focus on close.
- All `DESIGN.md` color-token pairs (button/status-badge foreground-on-background combinations, in both light and dark) must clear WCAG AA contrast — flagged here for a contrast-checker pass before build, since exact ratios weren't computed during this UX pass.
- Tables remain operable at 200% browser zoom without horizontal scroll trapping content (relevant given dense Dashboard/History layouts).

## Responsive & Platform

- Breakpoints follow MUI's defaults (`xs/sm/md/lg/xl`); no custom breakpoint scale introduced.
- Below `md`: sidebar becomes a drawer; below `sm`: the shared data-table pattern converts each row into a stacked key-value card (a 6-column Notification History table doesn't fit a phone width) — sort/filter controls move into a top toolbar rather than column headers.
- Dashboard stat tiles reflow from a multi-column grid (desktop) to a single column (mobile) without hiding any of the seven required fields (SM-C2) — order, not presence, changes across breakpoints.
- Dark mode follows system preference by default, with a manual override in Settings, persisted per Administrator account.

## Inspiration & Anti-patterns

From market positioning (addendum.md), not the user's direct naming — flagged as inferred, not elicited:

- **Anti-pattern:** heavy, configuration-dense enterprise pharma CRM suites (Veeva, Salesforce Life Sciences) — too much surface area for what this tool actually does. GrowthTrack should never grow a settings-within-settings maze to feel "serious."
- **Anti-pattern:** consumer-flashy WhatsApp broadcast/marketing platforms (Wati, AiSensy, SleekFlow) — those are built to sell growth marketing; GrowthTrack is an internal ops instrument reporting on sales growth, a different job that shouldn't borrow their promotional visual energy.
- **Reference point:** the more credible end of regional Sales-Force-Automation dashboards — functional, data-forward, unglamorous in the right way — executed with more current visual craft than that category typically shows.

## Key Flows

Journey names and beats mirror the PRD verbatim (§2.3); this section adds portal-screen specificity and ties each beat to the surfaces above.

**UJ-1. Rehana sends an urgent update the moment a target changes.** (`mockups/dashboard.html` → `mockups/notifications-compose.html`)
Entry: authenticated, on **Dashboard**. Path: Dashboard → **Notifications ▸ Compose** → selects the "Team B" **Recipient picker** entry → picks the pre-approved template → fills in the revised-target variable → optionally attaches the current report (with its generation date/period visible, per the edge case on stale-attachment confusion) → confirms via **Confirmation dialog**. Climax: she hits Send; the **in-progress state** ("Sending to N recipients…") resolves within minutes, well ahead of tomorrow's scheduled run. Resolution: the send appears immediately in **Notifications ▸ History**, tagged "Manual," each recipient's **status badge** visible individually. Edge case: one recipient's number is invalid — that one row shows `Failed — invalid number` via the status-badge pattern; it never blocks or delays the rest of the group's `Delivered` rows.

**UJ-2. Farhan reads his morning report before his first call.**
Entry: not authenticated to anything — this journey never touches the portal. Path: at the scheduled time, the **(WhatsApp) Daily Report** arrives, formatted per `sample-whatsapp-report.md` and governed conceptually by `DESIGN.md`'s tone (precise, no filler). Climax: in under a minute he knows where he stands and has his prioritized doctor list. Resolution: he heads out with a plan. Edge case: if his send fails and retries exhaust, the failure surfaces in Rehana's **Notification History** the same Operational Day — Farhan himself sees nothing (no message arrived), which is exactly why FR-11's same-day visibility to an Administrator matters.

**UJ-3. Rehana investigates a delivery gap.** (`mockups/notification-history.html`)
Entry: authenticated, on **Notifications ▸ History**. Path: filters by recipient and date (**Data table** filter toolbar) → finds the manager's row marked `Failed — retries exhausted` via the **status badge** → drills down (row expansion) to the logged reason, e.g. "invalid number." Climax: root cause identified from the log alone, no engineering escalation. Resolution: she opens **Recipients**, corrects the phone number in the **Directory form** (triggering fresh Opt-In Consent per FR-9's assumption), and — since this is exactly the kind of action FR-12 requires — can cross-check the change landed in the **Audit Log** from the same investigative session.
