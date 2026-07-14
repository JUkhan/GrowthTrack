---
title: GrowthTrack
status: final
created: 2026-07-14
updated: 2026-07-14
---

# PRD: GrowthTrack — Phase 1 (WhatsApp Sales Reporting & Admin Portal)
*Working title — confirm.*

## 0. Document Purpose

This PRD is for the PM, engineering/architecture, UX, and whoever builds the Phase 1 epics and stories. It builds directly on `_bmad-output/specs/spec-growthtrack/SPEC.md` and its companions (`entities.md`, `stack.md`, `architecture-diagrams.md`, `sample-whatsapp-report.md`, `roadmap-phase2.md`) — the reconciled contract distilled from two conflicting source SRS drafts — and does not duplicate their content wholesale. Market research, WhatsApp-provider comparison data, and options-considered rationale live in `addendum.md`; consult it for the *why* behind decisions this PRD states as fact. Vocabulary is Glossary-anchored (§3); Functional Requirements are grouped under Features (§4) and numbered globally (FR-1 through FR-12) so downstream artifacts have stable references; inferred details are tagged `[ASSUMPTION]` inline and indexed in §14.

## 1. Vision

Sales representatives, managers, and executives at a pharmaceutical/FMCG field sales organization currently lack timely visibility into daily sales performance, brand trends, and which doctors to prioritize for visits. GrowthTrack closes that gap by delivering that visibility automatically, every day, through the channel field staff already use — WhatsApp — instead of asking them to adopt a new app or log into a portal they'll never open between calls.

For administrators, GrowthTrack is a control plane: one place to manage who receives what, trigger an urgent update outside the daily schedule, and prove — via a complete audit trail — that every notification went out correctly. The Dashboard gives them today's live numbers; the Daily Report gives every recipient the cumulative picture (YTD/MTD sales, Achievement %, Growth %) plus synthesized guidance — which brands are winning, which need attention, and which doctors matter most this week per territory — turning a reporting tool into something closer to a daily briefing.

Phase 1 deliberately holds the line at reporting and management. AI-driven forecasting — the more ambitious half of the original concept — is real and wanted, and its candidate scope is fully preserved in `roadmap-phase2.md` (not yet validated as committed capabilities), but it depends on Phase 1's data pipeline and delivery infrastructure existing and working first. Shipping the reporting-and-management core cleanly is what makes Phase 2 possible, not a consolation scope cut.

## 2. Target User

### 2.1 Jobs To Be Done

- As a **Sales Rep**, I want to see my own and my team's performance every morning without logging into anything, so I can walk into my first call already informed.
- As a **Sales Rep**, I want a prioritized doctor list for my territory, so I know who to visit first today.
- As a **Manager**, I want visibility into team-wide achievement and growth trends, so I can coach reps proactively instead of finding out about a miss at month-end.
- As an **Administrator**, I want a single portal to manage who receives what and when, so recipient changes take effect without touching source data systems directly.
- As an **Administrator**, I want to trigger an urgent notification outside the daily schedule, so time-sensitive updates (a target revision, an urgent brand push) don't wait for tomorrow's run.
- As an **Administrator**, I want a complete, queryable history of every notification sent, so I can answer "did X receive Y" without guessing.

### 2.2 Non-Users (v1)

- **Doctors/HCPs** are not users of GrowthTrack — they are targeting data (a list reps use to plan visits), never a message recipient or portal user in Phase 1.
- **Sales Users and Managers** are not portal users in Phase 1 — they receive everything via WhatsApp; only Administrators authenticate to the web portal. (See §14 Assumptions Index and addendum §A5 for the reasoning.)

### 2.3 Key User Journeys

- **UJ-1. Rehana sends an urgent update the moment a target changes.**
  - **Persona + context:** Rehana, a regional sales administrator, just got word that Team B's quarterly target was revised mid-month. Reps need to know before tomorrow's scheduled report.
  - **Entry state:** Authenticated in the GrowthTrack portal, on the Dashboard.
  - **Path:** She opens Notifications → New Manual Notification, selects the "Team B" recipient group, writes a short note explaining the revised target, and optionally attaches the current performance report.
  - **Climax:** She hits Send; the message reaches every Team B recipient within minutes, well before the next scheduled run.
  - **Resolution:** The notification appears in Notification History immediately, tagged "Manual," so she can confirm delivery without waiting.
  - **Edge case:** If one recipient's number is invalid or unreachable, that single delivery is logged as failed with a retry attempt recorded — it doesn't block or delay delivery to the rest of the group.

- **UJ-2. Farhan reads his morning report before his first call.**
  - **Persona + context:** Farhan, a field sales rep, is having tea before heading out. He never logs into any GrowthTrack system directly.
  - **Entry state:** Not authenticated to anything — a WhatsApp message simply arrives.
  - **Path:** At the scheduled time, GrowthTrack's Daily Report lands in his WhatsApp: YTD/MTD sales, his Achievement % and Growth %, his team's standing, this month's top and focus brands, and a prioritized doctor list for his territory.
  - **Climax:** In under a minute of reading, he knows exactly where he stands and who to prioritize visiting today.
  - **Resolution:** He heads out with a concrete visit plan, no app-switching required.
  - **Edge case:** If the scheduled send fails for his number, the system retries automatically; if all retries are exhausted, the failure is logged and visible to Rehana in Notification History the same day.

- **UJ-3. Rehana investigates a delivery gap.**
  - **Persona + context:** A regional manager mentions he didn't get yesterday's report. Rehana needs to find out why, fast.
  - **Entry state:** Authenticated in the portal, on Notification History.
  - **Path:** She filters history by recipient and date, finds the manager's entry marked "Failed — retries exhausted," and checks the logged reason (e.g., invalid number).
  - **Climax:** She identifies the root cause (an outdated phone number) directly from the log — no need to check source data systems or ask engineering.
  - **Resolution:** She corrects the recipient's number in the directory (FR-9); the fix takes effect from the next send, scheduled or manual.

## 3. Glossary

- **Administrator** — The only role authenticated to the GrowthTrack web portal in Phase 1. Manages recipients, triggers manual notifications, and reviews history.
- **Sales User** — A field sales representative. Receives Daily Reports and any Manual Notifications via WhatsApp; no portal access in Phase 1.
- **Manager** — Oversees one or more Sales Teams. Receives WhatsApp content like a Sales User; no portal access in Phase 1.
- **Role** — Administrator, Sales User, or Manager. Stored per User; governs portal access (Administrator only) and content routing/formatting for WhatsApp delivery.
- **Recipient** — Any addressable target of a notification: an individual User, a Recipient Group, a Recipient Channel, or a Sales Team.
- **Recipient Group** — A named, GrowthTrack-internal saved set of individual Users, used as a single notification target. `[ASSUMPTION: not a live WhatsApp Group object addressed via a platform broadcast API — Twilio's WhatsApp product only supports sending template messages to individual phone numbers, so targeting a Recipient Group fans out to each member's individual number. See addendum §A6.]`
- **Recipient Channel** — A named, GrowthTrack-internal saved set of individual Users, used as a single notification target, distinguished from a Recipient Group only by naming/organizational convention (e.g., broadcast-style vs. team-style). Same fan-out mechanism and assumption as Recipient Group above.
- **Sales Team** — A named grouping of Sales Users (e.g., "Team A") used both for performance reporting and as a notification target.
- **Notification** — A message sent through GrowthTrack, either a **Scheduled Notification** (the automated Daily Report) or a **Manual Notification** (Administrator-triggered, ad hoc).
- **Daily Report** — The scheduled, formatted WhatsApp message sent to all configured Recipients once per day; content and layout match `sample-whatsapp-report.md`.
- **Dashboard** — The Administrator's single-screen summary view (§4.2).
- **Achievement %** — Actual sales against target, expressed as a percentage. Exact formula: `[ASSUMPTION]`, pending confirmation (§13).
- **Growth %** — Change in sales versus a prior period (Month-over-Month or Year-over-Year, depending on context). Exact formula: `[ASSUMPTION]`, pending confirmation (§13).
- **Territory** — A geographic or organizational sales region; scopes both team performance and the Doctor visit list.
- **Doctor** — A healthcare professional tracked as a visit target for Sales Users; not a GrowthTrack user or message recipient. Fields: Name, Territory, Target Priority.
- **Target Priority** — The ranking used to order the Doctor visit list within a Territory. (Source field: `Doctor.Priority` in `entities.md`.)
- **Brand** — A product brand tracked in sales data; classified as Top Brand, Low-Performing Brand, or Focus Brand (§4.3).
- **Source System** — The external system of record for sales, brand, and doctor/territory data feeding GrowthTrack. Not yet identified — `[ASSUMPTION]`, see §13.
- **WhatsApp Business Solution Provider (BSP)** — The vendor GrowthTrack uses to send WhatsApp messages. Twilio for Phase 1 (POC-only); production provider deferred (addendum §A2).
- **Opt-In Consent** — A Recipient's recorded agreement to receive WhatsApp messages from GrowthTrack, captured before delivery is enabled (FR-10).
- **Notification History** — The queryable log of every sent Notification (§4.8, FR-11).
- **Audit Log** — The queryable, append-only log of administrative actions (§4.8, FR-12), distinct from Notification History.
- **Send Event** — One Recipient's delivery obligation for one trigger (a single scheduled run, or a single Manual Notification send) — the unit that FR-6's "exactly one report," FR-7's no-duplicate guarantee, and SM-3 all apply to. A retry of a failed attempt is part of the same Send Event, not a new one.
- **Operational Day** — A calendar day in Asia/Dhaka time, used as the boundary for "same operational day" visibility requirements (FR-7, FR-11, SM-5).

## 4. Features

### 4.1 Authentication & Access Control
**Description:** Administrators authenticate with a username/password to obtain a JWT-based session; every portal route is gated behind that session. Sales User and Manager roles exist on the User record for content-routing purposes but do not authenticate to the portal in Phase 1 — they are WhatsApp-only recipients. `[ASSUMPTION: this resolves a tension in the source SPEC between CAP-1, which named only Administrator as a portal-login role, and a constraint requiring RBAC across all three roles — see addendum §A5 for the reconciliation rationale.]`

**Functional Requirements:**

#### FR-1: Administrator Login & Session
Administrator can authenticate with username/password and hold a JWT-based session — JWT is a direct requirement inherited from SPEC.md's CAP-1, not a PRD-level tech prescription. Realizes UJ-1, UJ-3.

**Consequences (testable):**
- Valid credentials return a JWT access token; invalid credentials are rejected and no session is issued.
- Unauthenticated requests to any portal route are rejected (never return portal content).
- A valid session expires or can be invalidated per policy — exact TTL is `[open question, §13]`.
- All requests carrying credentials or session tokens occur over HTTPS only.
- Passwords are stored encrypted at rest, never in plaintext.

#### FR-2: Role-Scoped Portal Access
Only the Administrator role is authorized to reach portal routes in Phase 1. Realizes UJ-1, UJ-3.

**Consequences (testable):**
- Every portal route enforces an Administrator-role check server-side, not just in the UI.
- Sales User and Manager accounts, if they exist, cannot obtain a portal session token.
- The Role field remains queryable for notification-routing logic used elsewhere (FR-6, FR-9).
- The last remaining Administrator account cannot be deleted or deactivated (FR-9) — the portal must always retain at least one working login path.

**Notes:** `[NOTE FOR PM]` If a future phase adds portal access for Managers or Sales Users, this FR's single-role gate must expand to true multi-role authorization — flagged in Non-Goals (§5) as deliberately deferred, not an oversight.

### 4.2 Performance Dashboard
**Description:** A single screen giving the Administrator everything needed to assess sales health at a glance, live rather than as of the last scheduled run. The Dashboard and the Daily Report (§4.5) are deliberately different views, not the same data twice: the Dashboard adds Today's Sales and current notification status — meaningful only in real time — while the Daily Report, generated once daily, presents the cumulative YTD/MTD picture without a same-day figure that wouldn't yet exist at send time.

**Functional Requirements:**

#### FR-3: Dashboard Summary View
Administrator can view a single dashboard summarizing Today's Sales, YTD Sales, MTD Sales, Achievement %, Growth %, team performance (by Sales Team), and notification status. Realizes UJ-1, UJ-3.

**Consequences (testable):**
- All seven fields render from current data within 3 seconds of page load, including Today's Sales and notification status — the two fields that are Dashboard-only and do not appear in the Daily Report (see §4.2).
- The Dashboard screen also includes Brand Performance (FR-4) as an additional section beyond these seven core fields — required because CAP-6 (SPEC.md) mandates Brand lists appear on both the Dashboard and the Daily Report. Doctor Visit Prioritization (FR-5) is Daily-Report-only per CAP-7 and is not required on the Dashboard. This resolves what would otherwise read as a contradiction between a fixed "seven fields" list and FR-4's Dashboard-availability claim.
- Sales figures are formatted in Cr BDT (Bangladeshi crore taka), consistent with §4.5/FR-6.
- Achievement % and Growth % use the formulas defined in §3 Glossary `[ASSUMPTION, pending confirmation — §13]`.
- Team performance is broken out per Sales Team.
- Notification status reflects the outcome of the most recent scheduled and manual sends.

### 4.3 Brand Performance Analytics
**Description:** Surfaces which brands are winning, which are lagging, and which the organization should be pushing right now — computed once, consumed by both the Dashboard and the Daily Report so the two never disagree.

**Functional Requirements:**

#### FR-4: Brand Performance Lists
System computes Top Brands, Low-Performing Brands, and Focus Brands from current sales data. Realizes UJ-2.

**Consequences (testable):**
- All three lists compute from a given dataset snapshot and are available to both the Dashboard (FR-3) and the Daily Report (FR-6).
- Each list entry includes Brand Name, Sales, Rank, and Growth.
- Ranking thresholds (what qualifies as "top," "low-performing," or "focus") are defined and documented before architecture work begins. `[NOTE FOR PM: neither source SRS defines these thresholds — needs a business decision, not an engineering guess.]`

### 4.4 Doctor Visit Prioritization
**Description:** Turns raw territory/doctor data into a ranked visit plan a Sales Rep can act on the same day, delivered as part of their Daily Report.

**Functional Requirements:**

#### FR-5: Prioritized Doctor List
System surfaces a doctor visit list per territory, ranked by Target Priority. Realizes UJ-2.

**Consequences (testable):**
- Each entry includes Doctor Name, Territory, and Target Priority.
- The list is scoped per Territory and reflected in the relevant recipient's Daily Report (FR-6).
- No patient health data is included or implied — Doctor records carry only name, territory, and priority.

### 4.5 Automated Daily WhatsApp Reporting
**Description:** The core delivery mechanism: once a day, every configured Recipient gets a correctly formatted, current report without anyone lifting a finger — reliably enough that Administrators can trust it and stop double-checking manually.

**Functional Requirements:**

#### FR-6: Scheduled Report Generation & Send
System automatically generates and sends a formatted Daily Report to configured Recipients on a fixed schedule. Realizes UJ-2.

**Consequences (testable):**
- Report format matches `sample-whatsapp-report.md` (YTD/MTD sales, Achievement %, Growth %, team performance, top/focus brand, doctor list).
- Sales figures are formatted in Cr BDT (Bangladeshi crore taka), matching `sample-whatsapp-report.md`'s example figures.
- Brand and doctor entries in the report are condensed to names only (per the sample format's WhatsApp-appropriate brevity); the full field set (Sales, Rank, Growth for brands; Territory, Target Priority for doctors — FR-4, FR-5) remains available on the Dashboard.
- Generation completes within 60 seconds of the scheduled trigger.
- A Recipient reachable through more than one targeting mechanism at once (e.g., as an individual and via a Sales Team) is de-duplicated to a single Send Event — never more than one report per Recipient per scheduled run.
- Each configured Recipient receives exactly one report within 5 minutes of the scheduled run; any retries triggered by FR-7 must complete within that same 5-minute window — a Send Event is not retried past it.
- The schedule is a single, global, Administrator-configurable time `[ASSUMPTION: default 07:00 Asia/Dhaka, pending confirmation — §13]`.

**Out of Scope:**
- Per-recipient schedule customization (see §5 Non-Goals).

#### FR-7: Delivery Retry & Failure Logging
Failed sends automatically retry, and every attempt is logged regardless of outcome — applies to both Scheduled Notifications (FR-6) and Manual Notifications (FR-8). Realizes UJ-1, UJ-3.

**Consequences (testable):**
- No duplicate notifications are sent for the same Send Event, including across retries.
- Failed sends retry automatically per a defined retry policy — attempt count and backoff are `[open question, §13]`.
- A Recipient whose retries are exhausted within the current Send Event is not automatically re-attempted until the next scheduled run (for Scheduled Notifications) or a fresh Administrator-triggered send (for Manual Notifications) — no silent indefinite retry.
- Every send attempt's outcome is visible in Notification History (FR-11) the same Operational Day.

### 4.6 Manual / Ad-Hoc Notifications
**Description:** Gives Administrators an escape hatch from the daily schedule — for urgent updates, corrections, or one-off announcements that shouldn't wait until tomorrow.

**Functional Requirements:**

#### FR-8: Compose & Send Manual Notification
Administrator can select Recipients, compose a custom message, optionally attach a report, and send immediately. Realizes UJ-1.

**Consequences (testable):**
- Dispatch begins within 60 seconds of Administrator confirmation `[ASSUMPTION: matches FR-6's generation window, pending confirmation — §13]` — the message reaches selected Recipients without waiting for the next scheduled run.
- Failed manual sends retry and log per FR-7, same as Scheduled Notifications.
- Sending is blocked if zero Recipients are selected.
- A Recipient selected through more than one mechanism in the same send (e.g., individually and via their Sales Team) is de-duplicated to a single message.
- Sent manual notifications appear in Notification History (FR-11) tagged "Manual."
- Recipient selection reuses the Recipient directory (FR-9) — individuals, groups, channels, or teams, selectable individually or in combination.

### 4.7 Recipient & Directory Management
**Description:** The Administrator's control over who is reachable and how — the directory every other feature's targeting logic draws from.

**Functional Requirements:**

#### FR-9: Manage Recipient Directory
Administrator can add, edit, or remove individual Users, Recipient Groups, Recipient Channels, and Sales Teams used to target notifications. Realizes UJ-1, UJ-3.

**Consequences (testable):**
- Adding, editing, or removing a recipient, group, channel, or team changes who future notifications (scheduled and manual) reach.
- User accounts are created manually by an Administrator in Phase 1 — no external directory sync. *(Confirmed with the user during PRD discovery; a decision, not an inferred assumption.)*
- Changing a Recipient's phone number requires fresh Opt-In Consent (FR-10) before delivery resumes to the new number `[ASSUMPTION: consent is tied to the number, not the person — pending confirmation, §13]`.
- Directory changes are captured in the Audit Log (FR-12).

#### FR-10: Recipient Opt-In Consent Capture
System captures and records a Recipient's opt-in consent before enabling WhatsApp delivery to them. `[ASSUMPTION: added to satisfy WhatsApp's business-messaging opt-in policy — not addressed by either source SRS. See addendum §A3.]`

**Consequences (testable):**
- A Recipient cannot receive Scheduled or Manual notifications until opt-in is recorded.
- Opt-out is possible and immediately stops future sends to that Recipient.
- Consent state is visible to the Administrator in the Recipient directory (FR-9).

### 4.8 Notification History & Audit
**Description:** The system of record for "what went out and what did we do" — the feature that turns "trust me" into "check the log," for both message delivery and administrative action.

**Functional Requirements:**

#### FR-11: Notification History
Administrator can view a full history of sent notifications: date, time, recipient, message type (Scheduled/Manual), and delivery status. Realizes UJ-3.

**Consequences (testable):**
- Every notification sent — scheduled or manual — appears in history with accurate status the same Operational Day.
- History is filterable by recipient, date range, and message type. `[NOTE FOR PM: filter fields are a reasonable default, not specified by either source SRS — confirm with an Administrator persona before UX work begins.]`

#### FR-12: Administrative Action Audit Log
All administrative actions are logged for audit. Realizes UJ-3.

**Consequences (testable):**
- Every create/edit/delete action on Recipients, Groups, Channels, or Teams is recorded with actor, timestamp, and what changed.
- Opt-in/opt-out status changes (FR-10) and Daily Report schedule changes (FR-6) are audited as administrative actions, not just directory CRUD.
- Login events are recorded.
- An administrative action and its Audit Log entry succeed or fail together — no action takes effect without a corresponding audit record.
- The Audit Log is append-only and viewable by Administrators.
- Retention period for audit records is defined before production launch — `[open question, §13]`.

## 5. Non-Goals (Explicit)

- **AI-based sales forecasting** — monthly/territory/brand-demand/target-achievement prediction, doctor potential scoring, low-sales alerts — is out of scope for Phase 1. Candidate scope fully preserved in `roadmap-phase2.md` (not yet validated as committed capabilities); Phase 1's data and delivery pipeline is what makes it buildable later.
- **Portal access for Sales Users and Managers** is out of scope for Phase 1 — WhatsApp-only delivery for these roles (§4.1, §14). `[NOTE FOR PM]` This may be emotionally load-bearing for Managers who want direct visibility rather than waiting for the daily WhatsApp send — worth revisiting if timeline or stakeholder pressure permits.
- **Interactive charting dashboard**, image-rich WhatsApp messages, Power BI integration, email notifications, push notifications, a native mobile app, per-recipient scheduled report customization, multi-language support, and PDF/Excel export are all out of scope for Phase 1 — listed as future enhancements by the source concept docs.
- **Production-grade WhatsApp Business Platform migration** is out of scope for Phase 1; Twilio is used as a POC-only provider (addendum §A2 preserves the production-decision comparison data for later).
- **External identity/SSO integration** is out of scope for Phase 1 — Administrator authentication is self-contained (username/password + JWT). `[ASSUMPTION]`
- **Messaging doctors/HCPs directly** is out of scope for Phase 1 and is not currently planned for any phase — the Doctor list is a targeting aid for reps' own visits, not a message recipient list (addendum §A3).

## 6. MVP Scope

### 6.1 In Scope
- Administrator authentication and role-scoped portal access (§4.1)
- Performance Dashboard (§4.2)
- Brand Performance Analytics (§4.3)
- Doctor Visit Prioritization (§4.4)
- Automated Daily WhatsApp Reporting, with retry and failure logging (§4.5)
- Manual / Ad-Hoc Notifications (§4.6)
- Recipient & Directory Management, including opt-in consent capture (§4.7)
- Notification History & Administrative Audit Log (§4.8)

### 6.2 Out of Scope for MVP
- Everything listed in §5 Non-Goals.
- **Manager-specific report content** — Phase 1's Daily Report (FR-6) is not differentiated by Role; a Manager overseeing multiple Sales Teams receives the same report shape as a Sales Rep, not an aggregated multi-team view. `[NON-GOAL for MVP]` The Manager JTBD (§2.1) is captured for context but does not drive a distinct FR in Phase 1 — worth revisiting once real Manager usage data exists.
- Any integration beyond receiving data from the (not yet identified) Source System — no bidirectional sync, no writing back to source systems.
- Any background-job infrastructure decision (e.g., Redis/Celery) — this is an architecture-level implementation choice, not a PRD-level scope item; the PRD requires only that retry/scheduling/idempotency guarantees (FR-6, FR-7) are met, not a specific mechanism.

## 7. Success Metrics

**Primary**
- **SM-1**: Daily Report delivery success rate — % of configured Recipients whose report is confirmed delivered (per BSP delivery-status callback) within 5 minutes of the scheduled run. Target ≥99%. Acknowledges this depends partly on Twilio/Meta/carrier reliability outside GrowthTrack's direct control — a shortfall should be triaged against BSP delivery-status data before being treated as a GrowthTrack defect. Validates FR-6, FR-7.
- **SM-2**: Dashboard load time — 95th-percentile page load ≤3 seconds. Validates FR-3.
- **SM-3**: Duplicate-send rate — notifications sent more than once for the same Send Event. Target: 0. Validates FR-7.

**Secondary**
- **SM-4**: Manual notification adoption — % of Administrators who send at least one manual notification per month, indicating the ad-hoc escape hatch is actually used, not just built. Validates FR-8.
- **SM-5**: History/audit completeness — % of sent notifications and administrative actions appearing in their respective logs the same Operational Day. Target 100%. Validates FR-11, FR-12.

**Counter-metrics (do not optimize)**
- **SM-C1**: Silent-failure rate — failed sends that are retried into eventual "success" without the original failure remaining visible. This must stay at 0; retry logic must never be tuned by hiding failures to make SM-1 look better. Counterbalances SM-1.
- **SM-C2**: Dashboard field completeness — all seven required fields (FR-3) must render every time; load-time optimization (SM-2) must never come at the cost of dropping or stubbing a field. Counterbalances SM-2.

## 8. Cross-Cutting NFRs

- **Performance:** Dashboard loads within 3 seconds; automated notification generation completes within 60 seconds; system supports 500+ concurrent WhatsApp-recipient dispatches per scheduled run `[ASSUMPTION: this SPEC-inherited figure describes recipient/dispatch fan-out capacity, not concurrent portal sessions — the Administrator-only portal population (§4.1) is inherently much smaller. Actual admin concurrency and the real recipient population size are open — §13.]`.
- **Reliability:** 99.5% uptime with automatic recovery after failures; no duplicate notifications for the same Send Event; failed sends auto-retry.
- **Security:** All communication over HTTPS; passwords encrypted at rest, never plaintext; role-based access control (Administrator-only portal access in Phase 1, JWT-based sessions); all administrative actions audit-logged.
- **Observability:** Notification delivery status and administrative actions are logged and queryable via Notification History (FR-11) and the Audit Log (FR-12) — no notification or admin action should be unaccounted-for after the fact.

## 9. Constraints and Guardrails

**Privacy**
- WhatsApp opt-in consent is required before any delivery to a Recipient (FR-10).
- No patient health data is collected or stored; the Doctor entity is limited to name, territory, and target priority.
- Data residency is addressed separately below (Data Governance) — it is a governance/legal question, not a per-feature privacy behavior.

**Cost**
- Every WhatsApp send — scheduled or manual — is a billed template message under Meta's per-message pricing model (effective 2025-07-01); cost scales with recipient count × send frequency. See addendum §A2 for provider cost comparison.
- The WhatsApp template category (Utility vs. Marketing) materially affects per-message cost and must be verified at WhatsApp Business Account setup, not assumed.
- No budget ceiling or monthly spend estimate is defined yet — neither source SRS nor Discovery surfaced a number, and no recipient-population figure exists to compute one from. `[open question, §13]`

## 10. Data Governance

- **Classification:** Sales figures, brand performance data, and doctor/territory targeting data are business-confidential; none of it is personal health information.
- **Residency:** Bangladesh's 2026 Personal Data Protection Act may require in-country residency for restricted/confidential data categories. GrowthTrack's data currently flows through Twilio/Meta infrastructure hosted outside Bangladesh. **Flagged as a pre-launch legal review item** (owner: legal/compliance) — not a hard Phase 1 NFR, and does not block PRD, architecture, or build work. See addendum §A4 for the full reasoning; if legal review requires localization, it will likely reshape the production WhatsApp provider decision (§A2).
- **Retention:** Retention period for sales data, Notification History, and Audit Log entries is not yet defined — `[open question, §13 below]`.

## 11. Integration and Dependencies

- **Source System:** The system of truth for sales, brand, and doctor/territory data is not yet identified — `architecture-diagrams.md` labels the upstream node only generically as "Sales Database." `[ASSUMPTION: some existing external system (ERP, CRM, or other database; name TBD), feeding GrowthTrack via nightly batch import — see Open Questions below.]`
- **Messaging:** Twilio WhatsApp API for Phase 1 (POC-only). Production provider decision deferred — see addendum §A2 for the comparison data (360dialog, Gupshup, Bangladesh-local BDT resellers).
- **Delivery-status feedback:** FR-7 and FR-11 require per-recipient delivery status, which needs an inbound integration point (e.g., a Twilio delivery-status webhook or polling) — a return path not represented in `architecture-diagrams.md`'s one-directional workflow diagram. To be resolved during architecture design.
- **Twilio credentials:** Secrets/credential management for the Twilio WhatsApp API (`stack.md` lists "Authentication" as one of its functions) is a Phase 1 integration dependency.
- **Identity:** No SSO or external identity provider in Phase 1; Administrator authentication is self-contained. `[ASSUMPTION]`

## 12. Operational Requirements

- **Uptime target:** 99.5%, with automatic recovery after failures.
- **Concurrency:** System supports 500+ concurrent WhatsApp-recipient dispatches per run (see §8 for the scope clarification); actual admin portal concurrency is much smaller and unspecified.
- **Support/on-call model and RTO/RPO** behind the uptime target are not yet defined — `[open question, §13 below]`.

## 13. Open Questions

1. What system is the source of truth for sales, brand, and doctor/territory data — ERP, CRM, a named system, or manual import? How often does it refresh? *(User did not answer during Discovery; §4.7/§11 currently run on an assumption — this is the highest-priority item to resolve before architecture work locks in an integration approach.)*
2. How exactly are Users mapped to Recipient Groups and Recipient Channels for targeting — is group/channel membership managed inside GrowthTrack's own directory, or does GrowthTrack just reference externally-managed WhatsApp Group/Channel IDs? Related: `entities.md`'s five-entity inventory (User, Notification, SalesData, BrandPerformance, Doctor) has no counterpart for Recipient Group or Recipient Channel today — both need a modeling decision before architecture proceeds.
3. What are the exact formulas for Achievement %, MoM Growth %, and YoY Growth %? (§3 Glossary, FR-3 currently assume standard percentage calculations.)
4. What time should the Daily Report run, and is a single global schedule (assumed) actually sufficient, or does some stakeholder need a different time? (FR-6 assumes 07:00 Asia/Dhaka.)
5. Bangladesh PDPA data residency — does GrowthTrack's data classification trigger the Act's localization requirement? Needs legal review before production launch (§10).
6. Which WhatsApp Business Solution Provider should be used for production (stay on Twilio, or migrate to 360dialog/Gupshup/a local BDT reseller)? Deferred past Phase 1 — see addendum §A2.
7. Is dedicated background-job infrastructure (e.g., Redis/Celery) needed to meet the retry/scheduling/idempotency requirements (FR-6, FR-7), or does a simpler mechanism suffice? Deferred to architecture.
8. Does `Team` need to be a standalone data entity (vs. a field on `SalesData`/`User`), and should `Notification` split into a template/history pair? Deferred to architecture — see `entities.md`. *(Note: FR-9/FR-12's CRUD-and-audit requirement for Sales Team is a product-level capability requirement, not a resolution of this modeling question — architecture remains free to implement Team as standalone or embedded.)*
9. What retention period applies to Notification History and Audit Log entries?
10. What support/on-call model and RTO/RPO targets sit behind the 99.5% uptime constraint?
11. What is the exact JWT session TTL and invalidation policy (FR-1)?
12. What retry policy (attempt count, backoff) governs failed WhatsApp sends (FR-7)?
13. What are realistic org-scale figures — Sales Rep/Manager/Administrator headcount, doctor count, territory count, and expected daily message volume? Several other open items (the §8 concurrency scope, the §9 cost ceiling, SM-4's statistical meaningfulness) can't be resolved without this.
14. Does Phase 1 need bulk import (e.g., CSV) for recipient onboarding, or is one-by-one manual entry (FR-9) sufficient at expected scale? Depends on Open Question 13.
15. What is the budget ceiling or expected monthly WhatsApp messaging spend? (§9 Cost)
16. What happens to a Recipient whose retries are exhausted within a Send Event — do they wait for the next scheduled run, or is there a manual-resend path? (FR-7)

A full edge-case hunt was run against FR-1 through FR-12 as part of the Reviewer Gate (44 findings, `review-edge-case-hunter.md`). The items above and the FR fixes already made absorb the load-bearing ones; the rest — password reset, login lockout, first-Administrator bootstrap, concurrent-edit locking, tie-break rules for brand/doctor ranking, empty-state rendering, phone-number uniqueness, list-truncation limits, and similar interaction-level details — are deliberately left to downstream UX/architecture/story-acceptance-criteria work rather than inflating this PRD's FRs. `review-edge-case-hunter.md` is required reading for whoever picks up `bmad-ux` or `bmad-create-epics-and-stories` next.

## 14. Assumptions Index

- §3/§4.2/§4.3 (FR-3) — Achievement % and Growth % use standard percentage formulas, pending business/finance confirmation.
- §4.1 (FR-1/FR-2) — `[ASSUMPTION]` OAuth2 is not required for Phase 1; JWT-based authentication alone is sufficient. Resolves a SPEC open question; consistent with CAP-1's explicit JWT commitment.
- §4.5 (FR-6) — Daily Report schedule is a single, global, Administrator-configurable time, default 07:00 Asia/Dhaka, with no per-recipient customization.
- §4.5 (FR-8) — Manual Notification dispatch begins within 60 seconds of Administrator confirmation, matching FR-6's generation window.
- §4.7/§11 — Source System for sales/brand/doctor data is some existing external system (ERP, CRM, or other database; name TBD), feeding GrowthTrack via nightly batch import.
- §3/§4.7 — Recipient Group and Recipient Channel are GrowthTrack-internal saved sets of individual Users (not live WhatsApp platform objects); targeting one fans out to each member's individual number via Twilio. See addendum §A6.
- §4.7 (FR-9) — Changing a Recipient's phone number requires fresh Opt-In Consent before delivery resumes to the new number; consent is tied to the number, not the person.
- §5/§11 — No SSO or external identity provider is required for Phase 1; Administrator authentication is self-contained.
- §4.2/§4.5 (FR-3, FR-6) — `[ASSUMPTION]` Currency formatting is Cr BDT (Bangladeshi crore taka), based on `sample-whatsapp-report.md`'s example figures — carries SPEC.md's Bangladesh-locale assumption forward explicitly.
- §8/§12 — "500+ concurrent users" (SPEC-inherited) is interpreted as WhatsApp-recipient dispatch fan-out capacity, not concurrent portal sessions, given the Administrator-only portal population established in §4.1.
- §5 — Pharma HCP promotional-compliance codes do not apply to Phase 1, since messages target internal staff (reps/managers/executives), not doctors directly. This is product-team reasoning, not a legal determination — re-examine if a future phase messages HCPs directly (see addendum §A3).
- §4.1 — RBAC is satisfied in Phase 1 by an Administrator-only portal gate; Sales User/Manager roles exist for content-routing, not portal authentication. *(User-confirmed during Discovery, not inferred — listed here for traceability since it resolves a SPEC-level ambiguity.)*
