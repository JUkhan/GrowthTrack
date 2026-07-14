---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-GrowthTrack-2026-07-14/prd.md
  - _bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/DESIGN.md
  - _bmad-output/planning-artifacts/ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md
  - _bmad-output/specs/spec-growthtrack/entities.md
  - _bmad-output/specs/spec-growthtrack/sample-whatsapp-report.md
---

# GrowthTrack - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for GrowthTrack Phase 1 (WhatsApp Sales Reporting & Admin Portal), decomposing the requirements from the PRD, UX Design contract, and Architecture spine into implementable stories.

## Requirements Inventory

### Functional Requirements

FR-1: Administrator can authenticate with username/password and hold a JWT-based session; unauthenticated requests to portal routes are rejected; a valid session expires or can be invalidated per policy.
FR-2: Only the Administrator role can reach portal routes in Phase 1; every portal route enforces the check server-side; the last remaining Administrator account cannot be deleted or deactivated.
FR-3: Administrator can view a single dashboard summarizing Today's Sales, YTD Sales, MTD Sales, Achievement %, Growth %, team performance, and notification status, all rendering within 3 seconds, plus Brand Performance as an additional section.
FR-4: System computes Top Brands, Low-Performing Brands, and Focus Brands from current sales data, available to both the Dashboard and the Daily Report.
FR-5: System surfaces a doctor visit list per territory, ranked by Target Priority, reflected in the relevant recipient's Daily Report.
FR-6: System automatically generates and sends a formatted Daily Report to configured Recipients on a fixed, Administrator-configurable schedule, de-duplicating recipients reachable through more than one targeting mechanism, completing generation within 60 seconds and delivery within 5 minutes.
FR-7: Failed sends (Scheduled or Manual) automatically retry and every attempt is logged; no duplicate notifications are sent for the same Send Event; a recipient whose retries are exhausted is not re-attempted until the next scheduled run or a fresh manual send.
FR-8: Administrator can select Recipients, compose a custom message, optionally attach a report, and send a Manual Notification immediately, reusing the Recipient directory; sending is blocked with zero Recipients selected.
FR-9: Administrator can add, edit, or remove individual Users, Recipient Groups, Recipient Channels, and Sales Teams; changes affect future notifications; changing a phone number requires fresh Opt-In Consent; all directory changes are audit-logged.
FR-10: System captures and records a Recipient's opt-in consent before enabling WhatsApp delivery; opt-out immediately stops future sends; consent state is visible in the Recipient directory.
FR-11: Administrator can view a full, filterable (recipient/date/type) history of sent notifications with date, time, recipient, message type, and delivery status, appearing the same Operational Day.
FR-12: All administrative actions (directory CRUD, opt-in/out changes, schedule changes, logins) are audit-logged with actor, timestamp, and what changed; an action and its audit entry succeed or fail together; the Audit Log is append-only.

### NonFunctional Requirements

NFR-1 (Performance): Dashboard loads within 3 seconds (95th percentile); automated notification generation completes within 60 seconds; system supports 500+ concurrent WhatsApp-recipient dispatches per scheduled run (fan-out capacity, not portal session concurrency).
NFR-2 (Reliability): 99.5% uptime with automatic recovery after failures; zero duplicate notifications for the same Send Event; failed sends auto-retry per a defined policy.
NFR-3 (Security): All communication over HTTPS; passwords stored encrypted, never plaintext; role-based access control (Administrator-only portal access in Phase 1); JWT-based sessions with invalidation-per-policy; all administrative actions audit-logged.
NFR-4 (Observability): Notification delivery status and administrative actions are logged and queryable via Notification History and the Audit Log — nothing sent or acted on is unaccounted-for after the fact.
NFR-5 (Privacy): WhatsApp opt-in consent required before any delivery; no patient health data collected or stored — the Doctor entity carries only name, territory, and priority.
NFR-6 (Cost): Every WhatsApp send (scheduled or manual) is a billed template message under Meta's per-message pricing; template category (Utility vs. Marketing) affects cost and must be verified at WhatsApp Business Account setup.
NFR-7 (Data Governance): Sales/brand/doctor data is business-confidential, not personal health information; Bangladesh PDPA residency is a flagged pre-launch legal-review item, not a hard Phase 1 constraint; retention periods for sales data, Notification History, and Audit Log are not yet defined.
NFR-8 (Concurrency): 500+ concurrent WhatsApp-recipient dispatches per scheduled run; actual admin-portal concurrency is much smaller and unspecified.

### Additional Requirements

- No starter template specified — greenfield hexagonal (ports & adapters) architecture. Epic 1 Story 1.0 (Project Scaffolding & Deployment Foundation) stands up the source tree fixed by the Architecture spine: `api/`, `domain/`, `ports/`, `adapters/whatsapp_twilio/`, `adapters/source_system/`, `adapters/persistence/`, `scheduler/`, `web/`, `alembic/`, `tests/`, `docker/`.
- Deployment: Docker Compose (API container, a **separate** scheduler container, PostgreSQL, Nginx reverse proxy terminating TLS, pinned ≥1.30.1/≥1.31.0 per CVE-2026-42945); staging and production environments share identical topology; every container declares a health check and `restart: always`; PostgreSQL is backed up via an automated daily dump to off-host storage (retention period open).
- Integration: Twilio WhatsApp API behind a `WhatsAppSender` port (`adapters/whatsapp_twilio/`); inbound Twilio delivery-status webhook (`POST /webhooks/twilio/status`) requiring signature verification, monotonic status transitions, and current-provider-SID matching; Source System nightly batch import (staging → validate → transform → upsert) behind a `SourceSystemImporter` port — the concrete system is not yet identified.
- Data setup/migration: Alembic-managed schema migrations; a staging-table layer ahead of the Source System upsert; soft-delete (`Status`/active flag) on `User`/`Team`/`RecipientList`, never hard delete.
- Monitoring/logging: a `/health` liveness endpoint polled by an external uptime monitor; structured JSON logging with a correlation/request id threaded from inbound HTTP or the scheduler trigger through to the WhatsApp adapter call.
- API conventions: REST plural-noun resources (`/recipients`, `/teams`, `/notifications/history`); one error envelope `{error:{code,message,details}}`; all entity ids UUIDv4; timestamps stored/transmitted as ISO 8601 UTC, converted to Asia/Dhaka only at presentation edges.
- Security implementation: one shared JWT + Administrator-role auth dependency with `jti`-keyed revocation (covers logout and mid-session deactivation); `pwdlib` (bcrypt) password hashing; the Audit Log write is co-transactional with every mutating action, including logins; opt-in consent is enforced during recipient resolution (before a `NotificationDelivery` row exists), never as a dispatch-time filter; zero-duplicate-send is guaranteed via partial unique indexes on `NotificationDelivery` plus an atomic claim step immediately before dispatch.
- Data model beyond `entities.md`: `RecipientList` (unifies Recipient Group/Channel), `Team` (standalone entity), `MessageTemplate` (approved template id + variable slots), `NotificationTarget` (relational target-spec join rows — never a JSON blob), `NotificationDelivery` (per-recipient Send Event record: status, attempt count, provider message SID, failure reason), an optimistic-concurrency version column on `User`/`Team`/`RecipientList`. Per AD-11: `PasswordResetToken` (standalone entity), `ReportSchedule` (standalone singleton), and `failed_login_count`/`locked_until`/`theme_preference` columns on `User`.
- Reference format: the Daily Report's exact content/layout must match `sample-whatsapp-report.md` (YTD/MTD sales, Achievement %, Growth %, team performance, condensed top/focus brand and doctor names, Cr BDT currency formatting).

### UX Design Requirements

UX-DR1: Implement brand color tokens as overrides on MUI's default theme (primary steel blue `#154D71`, accent growth green `#12966B`, status-warning `#C77700`, status-error `#C0362C`) with tuned dark-mode counterparts for each (not a naive lightness flip).
UX-DR2: Implement the `stat-display`/`stat-display-sm` typography tokens (32px/22px, semi-bold Roboto, tabular numerals) for all Dashboard headline figures and Daily Report numerals, so currency/percentage columns align vertically.
UX-DR3: Implement the `status-badge` component (success/warning/error variants), always pairing a color with an icon (check/clock/alert-triangle) and a text label — never color alone.
UX-DR4: Implement the `stat-tile` component: flat, bordered (no shadow), `rounded-md`, `stat-display` numeral, optional trend indicator (accent green up / status-error down, always paired with an up/down glyph).
UX-DR5: Implement the shared `data-table-row` pattern (sortable, filterable, dense) across Notification History, Recipients, and Audit Log — MUI `action.hover` on row hover, no custom striping.
UX-DR6: Apply flat/bordered surfaces by default (1px MUI divider border); reserve shadows only for modals, the recipient-picker popover, toasts/snackbars, and the mobile nav drawer.
UX-DR7: Apply shape tokens consistently: `rounded-md` (8px) default for buttons/inputs/stat-tiles, `rounded-lg` (12px) for modal/dialog containers only, `rounded-full` for status badges/pills only.
UX-DR8: Implement `button-primary` (single primary action per screen) and `button-danger` (destructive actions, always paired with a confirmation dialog) component variants.
UX-DR9: Support dark mode as a first-class target across all components/tokens — follows system preference by default, with a manual override in Settings persisted per Administrator account.
UX-DR10: Enforce a WCAG 2.1 AA accessibility floor on every color-token pair (button/status-badge foreground-on-background, light and dark) — a contrast-checker pass is required before build.
UX-DR11: Build the Information Architecture surfaces per the IA table: Login (incl. first-run bootstrap + password reset), Dashboard, Notifications▸Compose, Notifications▸History, Recipients, Audit Log, Settings — modal stacking limited to one level deep everywhere.
UX-DR12: Implement the Recipient picker component (shared between Notifications▸Compose and directory group/channel/team editing) showing a live de-duplicated count, e.g. "14 selected → 11 unique recipients (3 overlaps merged)".
UX-DR13: Implement the Notification composer restricted to pre-approved WhatsApp template selection plus variable-slot fill-in, with a live preview rendering exactly what the recipient will see — no free-form body text.
UX-DR14: Implement the Directory form with inline (on-blur) phone-number-uniqueness validation, and opt-in/consent state plus its timestamp shown directly in the form, not a separate tab.
UX-DR15: Implement the single shared Confirmation dialog pattern for every destructive/high-stakes action (delete recipient, deactivate-last-admin guard, opt-out, override a stale schedule) — names the real consequence, requires explicit confirm, uses `button-danger` only for the confirming action.
UX-DR16: Implement the Empty state pattern: zero Sales Teams/recipients/history/audit entries each get direct copy plus one primary action — no shared generic placeholder, no mascot/illustration.
UX-DR17: Implement the Loading state: skeleton stat tiles on Dashboard load targeting the ≤3s budget — no field is ever dropped to hit the budget faster; all seven required fields appear together, or none yet.
UX-DR18: Implement the Stale-data state: a "Data as of HH:MM" badge on the Dashboard when the Source System hasn't refreshed within its expected window (backed by the Architecture spine's last-successful-import timestamp).
UX-DR19: Implement the In-progress state: sending a Manual Notification disables the send control and shows "Sending to N recipients…" — no double-submit possible.
UX-DR20: Implement the Failed/retrying state via the `status-badge` pattern: `Queued → Sending → Delivered` / `Retrying (attempt n of N)` / `Failed — retries exhausted`, visually and textually distinct.
UX-DR21: Implement the Blocked state: zero recipients selected disables Send with an inline reason (not a silent no-op); deleting/deactivating the last Administrator is blocked with an explanatory tooltip.
UX-DR22: Implement the Conflict state: editing a Recipient record someone else just changed surfaces a conflict dialog showing both versions — never silently overwrites (backed by the Architecture spine's optimistic-concurrency version column).
UX-DR23: Implement Auth edge states: login lockout with a cooldown timer after repeated failed attempts; an Administrator deactivated mid-session is logged out on their next action with a plain explanation; zero Administrators routes Login to a one-time bootstrap flow.
UX-DR24: Implement responsive/platform behavior: MUI default breakpoints; sidebar collapses to a drawer below `md`; the shared data-table converts to a stacked key-value card below `sm` with sort/filter moved to a top toolbar; Dashboard stat tiles reflow multi-column to single-column without hiding any of the seven required fields (order changes, not presence).
UX-DR25: Implement voice-and-tone content requirements: error/failure copy names the actual cause ("Failed — invalid number", never "Something went wrong"); empty-state copy states what's missing plus the one resolving action; confirmation copy states the real consequence, not "Are you sure?"; numbers are never rounded away in copy.
UX-DR26: Implement full keyboard operability across all interactive controls (forms, composer, table filters, recipient picker) with `aria-label`s on icon-only controls, and correct focus trap/return on modal close.
UX-DR27: Restrict MUI snackbars to reversible, low-stakes confirmations only ("Recipient saved") — anything about delivery/send status lives as an in-page status badge, never a toast.

### FR Coverage Map

FR-1: Epic 1 - Administrator login & JWT session
FR-2: Epic 1 - Role-scoped portal access, last-admin guard
FR-3: Epic 2 - Dashboard summary view
FR-4: Epic 2 - Brand performance lists
FR-5: Epic 2 - Prioritized doctor list
FR-6: Epic 4 - Scheduled report generation & send
FR-7: Epic 4 - Delivery retry & failure logging
FR-8: Epic 4 - Compose & send manual notification
FR-9: Epic 3 - Manage recipient directory
FR-10: Epic 3 - Recipient opt-in consent capture
FR-11: Epic 5 - Notification history
FR-12: Epic 5 - Administrative action audit log

## Epic List

### Epic 1: Administrator Authentication & Access Control
Administrator can securely log into the GrowthTrack portal, hold a session, and every portal route is protected — the gate every other epic sits behind. Stands up the project's source tree and deployment foundation first, then covers first-run bootstrap (no Administrator exists yet), password reset, login lockout with cooldown, and the last-remaining-Administrator guard.
**FRs covered:** FR-1, FR-2

### Epic 2: Sales Performance Dashboard & Analytics
Administrator can see Today's/YTD/MTD sales, Achievement %, Growth %, team performance, top/low-performing/focus brands, and a territory-scoped, priority-ranked doctor visit list — the business-visibility core of the product, live rather than as-of-last-report.
**FRs covered:** FR-3, FR-4, FR-5

### Epic 3: Recipient & Directory Management
Administrator can manage individual Users, Sales Teams, Recipient Groups, and Recipient Channels, and capture/revoke WhatsApp opt-in consent — the addressable-target directory every notification (scheduled or manual) draws from.
**FRs covered:** FR-9, FR-10

### Epic 4: Automated & Manual WhatsApp Notifications
Every configured Recipient gets an accurate, correctly formatted Daily Report automatically, every day, with failures retried and logged — and the Administrator can trigger an urgent Manual Notification at any time outside that schedule. Consolidated into one epic (not two) because both paths share the same delivery, retry, and zero-duplicate-send mechanism end to end.
**FRs covered:** FR-6, FR-7, FR-8

### Epic 5: Notification History & Administrative Audit
Administrator can look up exactly what was sent to whom and when, and produce a complete, append-only record of every administrative action (directory changes, opt-in/out, schedule changes, logins) — turning "trust me" into "check the log."
**FRs covered:** FR-11, FR-12

## Epic 1: Administrator Authentication & Access Control

Administrator can securely log into the GrowthTrack portal, hold a session, and every portal route is protected — the gate every other epic sits behind. Stands up the project's source tree and deployment foundation first, then covers first-run bootstrap, password reset, login lockout, and the last-remaining-Administrator guard.

### Story 1.0: Project Scaffolding & Deployment Foundation

As a developer setting up GrowthTrack,
I want the source tree, Docker Compose deployment topology, and baseline database migration stood up exactly as the Architecture spine specifies,
So that every other story — in this epic and every epic after it — has a working, deployable foundation to build on, rather than each one improvising its own.

**Acceptance Criteria:**

**Given** a fresh repository checkout
**When** the project is scaffolded
**Then** the source tree matches the Architecture spine's structure exactly: `api/`, `domain/`, `ports/`, `adapters/whatsapp_twilio/`, `adapters/source_system/`, `adapters/persistence/`, `scheduler/`, `web/`, `alembic/`, `tests/`, `docker/` — with `domain/` importing only from `ports/`, per AD-1

**Given** the Docker Compose topology
**When** it is defined
**Then** it includes an API container, a **separate** scheduler container, PostgreSQL, and an Nginx reverse proxy terminating TLS (pinned ≥1.30.1/≥1.31.0 per CVE-2026-42945) — staging and production run the identical topology

**Given** any container in the compose topology
**When** it is defined
**Then** it declares a health check and a `restart: always` policy (AD-10)

**Given** the API service
**When** it starts
**Then** it exposes a `/health` liveness endpoint suitable for polling by an external uptime monitor

**Given** the database layer
**When** it is provisioned
**Then** Alembic is initialized with a baseline migration, and PostgreSQL is backed up via an automated daily dump to off-host storage (AD-10)

**Given** the repository
**When** code is pushed
**Then** a CI pipeline runs linting, type checks, and the automated test suite, blocking merge on failure — the specific CI provider is an implementation choice, not fixed by the Architecture spine

**Given** this story is complete
**When** any later story in any epic begins implementation
**Then** it builds directly on this source tree and deployment topology — no later story re-establishes project structure, container topology, or CI configuration

### Story 1.1: Administrator Login & Session

As an Administrator,
I want to log in with my username and password and receive a session,
So that I can access the GrowthTrack portal securely.

**Acceptance Criteria:**

**Given** valid Administrator credentials
**When** I submit the login form
**Then** I receive a JWT access token
**And** the exchange occurs over HTTPS only

**Given** invalid credentials
**When** I submit the login form
**Then** the request is rejected
**And** no session token is issued
**And** no information leaks about whether the username exists

**Given** no valid session
**When** I request any portal route
**Then** the request is rejected
**And** no portal content is returned

**Given** a stored Administrator password
**When** it is persisted
**Then** it is hashed with pwdlib (bcrypt backend), never stored in plaintext

### Story 1.2: First-Run Administrator Bootstrap

As a new GrowthTrack deployment with no Administrator account yet,
I want the Login screen to route to a one-time bootstrap flow,
So that the first Administrator can be created without a dead end.

**Acceptance Criteria:**

**Given** zero Administrator accounts exist
**When** I visit Login
**Then** I am routed to a one-time bootstrap flow instead of the standard form

**Given** the bootstrap flow
**When** I submit a valid new Administrator username/password
**Then** the first Administrator account is created
**And** I am logged in via Story 1.1's session mechanism

**Given** at least one Administrator already exists
**When** I visit Login
**Then** the standard login form is shown, not bootstrap

### Story 1.3: Role-Scoped Portal Access & Last-Admin Guard

As the system,
I want every portal route to enforce an Administrator-role check server-side and protect the last remaining Administrator account,
So that Phase 1's single-role RBAC story holds without exception.

**Acceptance Criteria:**

**Given** a Sales User or Manager account
**When** it attempts to obtain a portal session token
**Then** the request is rejected

**Given** any portal route
**When** it is implemented
**Then** it depends on one shared Administrator-role-checking dependency, never an inline per-route check

**Given** exactly one active Administrator remains
**When** an attempt is made to delete or deactivate that account
**Then** it is blocked with an explanatory message

### Story 1.4: Session Invalidation — Logout & Revocation

As an Administrator,
I want to log out, and to be logged out automatically if my account is deactivated mid-session,
So that a session can always be invalidated per policy, not just left to expire naturally.

**Acceptance Criteria:**

**Given** an active session
**When** I log out
**Then** a revocation record is written keyed by the session's JWT `jti`
**And** the shared auth dependency rejects that `jti` on any subsequent request, even before natural expiry

**Given** an Administrator is deactivated while holding an active session
**When** their next action reaches the portal
**Then** they are logged out with a plain-language explanation, not a silent redirect

### Story 1.5: Login Lockout & Password Reset

As an Administrator,
I want repeated failed login attempts to trigger a temporary lockout, and a way to reset a forgotten password,
So that I'm not permanently locked out while brute-force attempts are slowed.

**Acceptance Criteria:**

**Given** 5 failed login attempts for the same account within a 15-minute window `[ASSUMPTION: lockout threshold, pending confirmation — mirrors PRD §13's open-question pattern]`
**When** the 6th attempt is made
**Then** further attempts for that account are blocked for 15 minutes, tracked via `User.failed_login_count`/`locked_until` (Architecture spine AD-11)
**And** a cooldown timer counting down the remaining lockout time is shown, not a bare "try again" loop

**Given** a forgotten password
**When** I use the reset flow
**Then** I can set a new password through a secure, time-limited reset path backed by a single-use `PasswordResetToken` (Architecture spine AD-11) that expires 1 hour after issuance `[ASSUMPTION: reset-token TTL, pending confirmation]`
**And** it is hashed per Story 1.1's rule

### Story 1.6: Design System Foundation & Shared Interaction Patterns

As an Administrator,
I want the portal's shared visual language and interaction patterns established consistently,
So that every screen reads as one trustworthy instrument, not a patchwork of ad hoc UI.

**Acceptance Criteria:**

**Given** the MUI theme
**When** brand tokens are applied
**Then** primary steel blue, accent growth green, status-warning, and status-error colors (with tuned dark-mode counterparts) override MUI defaults; all unlisted tokens inherit MUI's defaults unchanged

**Given** headline figures anywhere in the portal
**When** rendered
**Then** they use the stat-display/stat-display-sm typography tokens (tabular numerals) so currency/percentage columns align vertically

**Given** buttons, inputs, stat-tiles, modals, and status badges
**When** rendered
**Then** they use the shape tokens consistently (rounded-md default, rounded-lg for modal containers only, rounded-full for badges/pills only) and flat/bordered surfaces by default, with shadows reserved for modals/popovers/toasts/the mobile nav drawer

**Given** a single primary action on a screen
**When** rendered
**Then** it uses button-primary; a destructive action uses button-danger and is always paired with the shared Confirmation dialog naming the real consequence, never a bare "Are you sure?"

**Given** a screen with zero data (no Sales Teams, recipients, history, or audit entries)
**When** rendered
**Then** it shows direct copy plus one primary action specific to what's missing — never a shared generic placeholder or mascot

**Given** the portal's theme
**When** toggled
**Then** dark mode follows system preference by default with a manual per-Administrator override, persisted in Settings via the `User.theme_preference` column (Architecture spine AD-11)

**Given** any color-token pair used for a button or status badge, in both light and dark
**When** contrast is checked
**Then** it clears WCAG 2.1 AA

**Given** the shared data-table pattern
**When** the viewport narrows below `sm`
**Then** each row converts to a stacked key-value card, with sort/filter controls moving into a top toolbar

**Given** any interactive control across the portal
**When** operated via keyboard alone
**Then** it is fully operable, with `aria-label`s on icon-only controls and correct focus trap/return on modal close

**Given** delivery/send status anywhere in the portal
**When** shown
**Then** it lives as an in-page status badge, never a toast; MUI snackbars are reserved for reversible, low-stakes confirmations only

**Given** error, empty-state, or confirmation copy anywhere in the portal
**When** written
**Then** it names the actual cause or consequence directly — never "Something went wrong" or "Are you sure?" — and numbers are never rounded away

## Epic 2: Sales Performance Dashboard & Analytics

Administrator can see Today's/YTD/MTD sales, Achievement %, Growth %, team performance, top/low-performing/focus brands, and a territory-scoped, priority-ranked doctor visit list — the business-visibility core of the product, live rather than as-of-last-report.

### Story 2.1: Nightly Sales & Reference Data Ingestion

As an Administrator,
I want sales, brand performance, and doctor/territory data ingested from the Source System every night,
So that the Dashboard and Daily Report always reflect current business data, not stale or manually-entered numbers.

**Acceptance Criteria:**

**Given** the nightly batch import runs
**When** it lands Source System data
**Then** it is staged, validated, transformed, then upserted into `SalesData`/`BrandPerformance`/`Doctor` via the same repository ports every other write path uses — never a direct write to live tables

**Given** an import completes successfully
**When** it finishes
**Then** its completion timestamp is recorded (backs the Dashboard's "Data as of HH:MM" badge)

**Given** malformed records in a source batch
**When** validation runs
**Then** invalid records are rejected and logged, not silently upserted, while valid records in the same batch still proceed

### Story 2.2: Dashboard Summary View

As an Administrator,
I want a single dashboard summarizing Today's Sales, YTD Sales, MTD Sales, Achievement %, Growth %, team performance, and notification status,
So that I can assess sales health at a glance.

**Acceptance Criteria:**

**Given** current sales data exists
**When** I open the Dashboard
**Then** all seven fields render within 3 seconds

**Given** the Dashboard is loading
**When** data hasn't arrived yet
**Then** skeleton stat tiles are shown for all seven fields together — never a partial render

**Given** the last import is older than its expected refresh window
**When** I view the Dashboard
**Then** a "Data as of HH:MM" badge is shown, rather than presenting stale numbers as current

**Given** the viewport narrows below `md`
**When** I view the Dashboard
**Then** stat tiles reflow to single-column without hiding any of the seven fields

**Given** no notification has been sent yet (Epic 4 not yet built or no send has occurred)
**When** the notification-status field renders
**Then** it shows a neutral "No sends yet" state rather than erroring — the field's live wiring to actual send outcomes is completed in Epic 4 (Stories 4.1/4.2), which is a backward extension of this story, not a forward dependency of it

**Given** the exact Achievement % and Growth % formulas are unconfirmed (PRD §13.3, `[ASSUMPTION, pending confirmation]`)
**When** this story is picked up for implementation
**Then** the formulas are confirmed by a finance/business stakeholder first — this story is not marked done on an engineering-assumed standard-percentage formula without sign-off; track as a pre-implementation blocker, not a silent default

### Story 2.3: Brand Performance Analytics

As an Administrator,
I want to see Top Brands, Low-Performing Brands, and Focus Brands computed from current sales data,
So that I know which brands are winning, lagging, or need a push right now.

**Acceptance Criteria:**

**Given** a current sales dataset
**When** brand rankings are computed
**Then** all three lists are produced from one computation shared by the Dashboard and Daily Report — they never disagree

**Given** a brand list entry
**When** displayed
**Then** it includes Brand Name, Sales, Rank, and Growth

**Given** the Dashboard's Brand Performance section
**When** it renders
**Then** it appears as an additional section beyond the seven core fields

**Given** the ranking thresholds that define "top," "low-performing," and "focus" brands are unconfirmed (PRD §4.3 note: "neither source SRS defines these thresholds — needs a business decision, not an engineering guess")
**When** this story is picked up for implementation
**Then** the thresholds are confirmed by a business/product stakeholder first — this story is not marked done with engineering-guessed thresholds; track as a pre-implementation blocker, not an inferred default

### Story 2.4: Prioritized Doctor Visit List

As an Administrator,
I want a doctor visit list computed per territory and ranked by Target Priority,
So that each Sales Rep's Daily Report reflects accurate, prioritized visit guidance.

**Acceptance Criteria:**

**Given** current doctor/territory data
**When** the visit list is computed for a territory
**Then** each entry includes Doctor Name, Territory, and Target Priority, ranked by priority

**Given** a doctor record
**When** stored or displayed
**Then** it contains no patient health data — only name, territory, and priority

**Given** the doctor list is computed
**When** consumed downstream
**Then** it feeds Epic 4's Daily Report generation and is not rendered as its own Dashboard/portal screen (Daily-Report-only)

**Given** this story ships before Epic 4 exists
**When** its correctness is verified
**Then** verification happens via automated tests against the domain computation and repository layer directly (ranking output for a known fixture territory/dataset) — this story's acceptance does not wait on Epic 4's Daily Report to visually confirm the list, since no portal screen will ever exist to check it against

## Epic 3: Recipient & Directory Management

Administrator can manage individual Users, Sales Teams, Recipient Groups, and Recipient Channels, and capture/revoke WhatsApp opt-in consent — the addressable-target directory every notification (scheduled or manual) draws from.

### Story 3.1: Manage Users & Sales Teams

As an Administrator,
I want to add, edit, and remove individual Users and Sales Teams,
So that the directory reflects who's actually on the ground and how they're organized.

**Acceptance Criteria:**

**Given** a new User (Name, Mobile, Role, Team)
**When** I submit the Directory form
**Then** the User is created, phone-number uniqueness is validated inline on blur, and the change is audit-logged in the same transaction as the write

**Given** an existing User or Team
**When** I edit or remove it
**Then** the change takes effect for future notifications and reporting, and is audit-logged co-transactionally

**Given** a User or Team is removed
**When** the removal is processed
**Then** it is soft-deleted, never hard-deleted, so notification/audit history referencing it is never orphaned

**Given** a Sales Team
**When** created, edited, or removed
**Then** the same CRUD-and-audit guarantees apply as for a User

### Story 3.2: Manage Recipient Groups & Channels

As an Administrator,
I want to create, edit, and remove Recipient Groups and Recipient Channels as named sets of Users,
So that I can target a group with one selection instead of picking individuals every time.

**Acceptance Criteria:**

**Given** a set of existing Users
**When** I create a Recipient Group or Channel
**Then** it is saved as a `RecipientList` with a `kind` field distinguishing them for display only — both share the same fan-out mechanism

**Given** an existing `RecipientList`
**When** I edit its membership or remove it
**Then** the change reaches future notifications, and is audit-logged co-transactionally

**Given** a `RecipientList` is removed
**When** processed
**Then** it is soft-deleted, never hard-deleted

### Story 3.3: Recipient Opt-In Consent Capture

As an Administrator,
I want to capture, view, and revoke a Recipient's WhatsApp opt-in consent,
So that no one receives a message from GrowthTrack without recorded consent.

**Acceptance Criteria:**

**Given** a User with no recorded consent
**When** I record opt-in consent (with a timestamp)
**Then** that User becomes eligible to receive Scheduled or Manual notifications

**Given** a User's consent is revoked
**When** the change is saved
**Then** future sends to that User stop immediately, audit-logged co-transactionally

**Given** a User's phone number is changed
**When** saved
**Then** existing consent is revoked automatically, and delivery is blocked until fresh consent is recorded for the new number

**Given** a User's record
**When** viewed
**Then** consent state and its timestamp are shown directly in the form, not a separate tab

### Story 3.4: Concurrent-Edit Conflict Detection

As an Administrator,
I want to be warned if I try to save a record someone else already changed,
So that I never silently overwrite a teammate's edit.

**Acceptance Criteria:**

**Given** a User, Team, or `RecipientList` with a version column
**When** two Administrators load the same record and one saves first
**Then** the second save is rejected as a conflict, not silently applied

**Given** a save conflict
**When** surfaced
**Then** a conflict dialog shows both versions and requires an explicit choice — never a silent overwrite

## Epic 4: Automated & Manual WhatsApp Notifications

Every configured Recipient gets an accurate, correctly formatted Daily Report automatically, every day, with failures retried and logged — and the Administrator can trigger an urgent Manual Notification at any time outside that schedule. Consolidated into one epic because both paths share the same delivery, retry, and zero-duplicate-send mechanism end to end.

### Story 4.1: Compose & Send Manual Notification

As an Administrator,
I want to select Recipients, pick a pre-approved template, fill in its variables, optionally attach the current report, and send immediately,
So that an urgent update reaches the right people without waiting for the next scheduled run.

**Acceptance Criteria:**

**Given** the Recipient picker
**When** I select a mix of individual Users, Teams, and RecipientLists
**Then** a live de-duplicated count is shown (e.g. "14 selected → 11 unique recipients (3 overlaps merged)") using the same resolution logic the send path uses

**Given** zero recipients selected
**When** I attempt to send
**Then** Send is disabled with an inline reason, not a silent no-op

**Given** a set of resolved recipients
**When** I confirm Send
**Then** one `Notification` row is created, recipients are resolved fresh (deduped, consent-filtered) into one `NotificationDelivery` row each, keyed uniquely by `(recipient_user_id, notification_id)`

**Given** the composer
**When** I compose a message
**Then** I select from pre-approved WhatsApp templates and fill its variable slots only — no free-form body text — with a live preview of exactly what the recipient will see

**Given** I confirm Send
**When** dispatch begins
**Then** the Send control is disabled and shows "Sending to N recipients…" — no double-submit is possible

**Given** each `NotificationDelivery` row is ready to dispatch
**When** the WhatsApp adapter is called
**Then** the row is atomically claimed first (conditional UPDATE) so a crashed/racing retry can never re-dispatch against the same row

**Given** a sent Manual Notification
**When** it completes
**Then** it appears in Notification History tagged "Manual"

**Given** a Manual Notification's send outcome
**When** it is the most recent send system-wide
**Then** the Dashboard's notification-status field (Story 2.2) reflects it, replacing the "No sends yet" placeholder

### Story 4.2: Automated Daily Report Generation & Send

As an Administrator,
I want every configured Recipient to automatically receive a correctly formatted Daily Report once a day,
So that the team stays informed without anyone manually triggering it.

**Acceptance Criteria:**

**Given** the scheduled trigger time arrives (once per operational day)
**When** the scheduler fires
**Then** a Scheduled Notification is created, targeting all configured Recipients, and generation completes within 60 seconds

**Given** the Daily Report content
**When** it is generated
**Then** it matches `sample-whatsapp-report.md`'s format and figures (YTD/MTD sales, Achievement %, Growth %, team performance, condensed top/focus brand and doctor names, Cr BDT currency formatting) sourced from Epic 2's computed data

**Given** a Recipient reachable via more than one targeting mechanism (individual + Team, e.g.)
**When** recipients are resolved for the day's run
**Then** they are de-duplicated to exactly one `NotificationDelivery` row, keyed by `(recipient_user_id, operational_day)`

**Given** the Send Event uniqueness constraint
**When** the scheduler restarts or fires twice for the same operational day
**Then** no duplicate `NotificationDelivery` rows are created — the partial unique index rejects the duplicate

**Given** delivery begins
**When** each recipient's send completes
**Then** it lands in Notification History tagged "Scheduled" within 5 minutes of the scheduled time
**And** the Dashboard's notification-status field (Story 2.2) reflects this run's outcome once it is the most recent send system-wide

### Story 4.3: Delivery-Status Webhook & Automatic Retry

As an Administrator,
I want failed sends to retry automatically and every attempt's outcome to be tracked accurately,
So that I can trust the delivery status shown without double-checking manually.

**Acceptance Criteria:**

**Given** Twilio sends a delivery-status callback
**When** it hits `POST /webhooks/twilio/status`
**Then** the request's signature is verified before any status update is applied

**Given** a status callback payload
**When** its provider message SID doesn't match the `NotificationDelivery` row's current SID
**Then** it is logged and ignored as a superseded/stale attempt

**Given** a status callback attempting to move status backward (e.g. Delivered → Queued)
**When** it is evaluated
**Then** it is rejected — status transitions are monotonic (`Queued → Sending → Delivered / Retrying / Failed`)

**Given** a send attempt fails
**When** retry is eligible
**Then** it is retried automatically for up to 3 additional attempts with exponential backoff (1 minute, 5 minutes, 15 minutes) `[ASSUMPTION: retry policy magnitude, pending confirmation — PRD §13.12]`, with every attempt logged regardless of outcome

**Given** a `NotificationDelivery`'s retries are exhausted within its Send Event
**When** the final attempt fails
**Then** it is left `Failed` and is not re-claimed until the next eligible Send Event (next operational day, or a fresh Manual Notification)

### Story 4.4: Daily Report Schedule Configuration

As an Administrator,
I want to view and change the Daily Report's global send time,
So that I can adjust when the team receives it without needing engineering involved.

**Acceptance Criteria:**

**Given** the current Daily Report schedule
**When** I open Settings
**Then** I can see the configured send time

**Given** a new send time
**When** I save it
**Then** it becomes the schedule the next scheduler run uses, and the change is audit-logged co-transactionally

**Given** the Daily Report schedule
**When** it is stored
**Then** it is a single, global setting persisted in the `ReportSchedule` entity (Architecture spine AD-11), not an environment variable — no per-recipient customization exists in Phase 1, and no redeploy is required to change it

## Epic 5: Notification History & Administrative Audit

Administrator can look up exactly what was sent to whom and when, and produce a complete, append-only record of every administrative action (directory changes, opt-in/out, schedule changes, logins) — turning "trust me" into "check the log."

### Story 5.1: Notification History View

As an Administrator,
I want to view a full, filterable history of every notification GrowthTrack has sent,
So that I can answer "did X receive Y" without guessing.

**Acceptance Criteria:**

**Given** notifications have been sent (scheduled or manual)
**When** I open Notifications ▸ History
**Then** every send — scheduled or manual — appears with date, time, recipient, message type, and delivery status, visible the same Operational Day it occurred

**Given** the History table
**When** I filter it
**Then** I can filter by recipient, date range, and message type

**Given** a Notification sent to a Team or RecipientList
**When** I view its History row
**Then** it drills down (row expansion) into one row per individual recipient outcome, so group sends are auditable down to the individual

**Given** the History table's status column
**When** any row is displayed
**Then** delivery status uses the status-badge pattern (color + icon + text label) — never color alone

### Story 5.2: Administrative Action Audit Log View

As an Administrator,
I want a complete, append-only log of every administrative action including logins,
So that I can prove exactly what happened and when, not just trust that it did.

**Acceptance Criteria:**

**Given** any create/edit/delete action on Recipients, Groups, Channels, or Teams (Epic 3), any opt-in/out change (Epic 3), any Daily Report schedule change (Epic 4), or any login (Epic 1)
**When** the action occurs
**Then** it is recorded in the Audit Log with actor, timestamp, and what changed, in the same transaction as the action itself

**Given** the Audit Log
**When** I view it
**Then** it is append-only and viewable by Administrators, with no edit or delete capability exposed anywhere

**Given** an administrative action
**When** its corresponding write fails
**Then** no partial state exists — the action and its audit entry succeed or fail together, never one without the other
