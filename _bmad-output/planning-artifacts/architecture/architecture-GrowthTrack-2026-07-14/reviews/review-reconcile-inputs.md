---
name: Reconcile-Inputs Review
subject: ARCHITECTURE-SPINE.md (GrowthTrack Phase 1)
against:
  - specs/spec-growthtrack/SPEC.md
  - specs/spec-growthtrack/entities.md
  - specs/spec-growthtrack/stack.md
  - specs/spec-growthtrack/architecture-diagrams.md
  - prds/prd-GrowthTrack-2026-07-14/prd.md
  - ux-designs/ux-GrowthTrack-2026-07-14/DESIGN.md
  - ux-designs/ux-GrowthTrack-2026-07-14/EXPERIENCE.md
date: 2026-07-14
---

# Reconciliation Review — ARCHITECTURE-SPINE.md vs. Source Inputs

## Verdict

The spine's structural skeleton (hexagonal boundaries, Send Event/idempotency model, entity ownership split, deployment topology) is sound and internally consistent, and it correctly closes the two genuinely-open modeling questions (PRD OQ#2, OQ#8) it claims to close — but it silently drops several load-bearing, testable requirements from the PRD and EXPERIENCE.md, most seriously the entire Opt-In/Opt-Out consent mechanism (FR-10, and FR-9's phone-number-change consequence), HTTPS/TLS as an explicit constraint, optimistic-concurrency for the UX's mandatory "conflict" edit-detection dialog, and audit coverage for login events (which FR-12 explicitly requires but AD-7's rule text doesn't trigger on). One capability (CAP-1 through CAP-8) map is complete; one functional requirement (FR-10) has no architectural home at all.

---

## 1. Capability Map Coverage (SPEC.md CAP-1 → CAP-8)

All eight capabilities appear in the spine's Capability → Architecture Map. Confirmed:

| Capability | Present in map? | Notes |
|---|---|---|
| CAP-1 (JWT auth) | Yes | `api/auth`, `ports/auth`, AD-8 |
| CAP-2 (Dashboard) | Yes | `api/dashboard`, `domain/metrics`, AD-1/AD-6 |
| CAP-3 (Automated daily report) | Yes | `scheduler/`, `domain/notifications`, AD-1/AD-2/AD-3 |
| CAP-4 (Manual notification) | Yes | `api/notifications`, `domain/notifications`, AD-1/AD-2/AD-3 |
| CAP-5 (Recipient directory mgmt) | Yes | `api/recipients`, `domain/recipients`, AD-4/AD-7 |
| CAP-6 (Brand analytics) | Yes | `domain/metrics`, AD-1/AD-6 |
| CAP-7 (Doctor visit list) | Yes | `domain/metrics`, AD-1/AD-6 |
| CAP-8 (Notification history) | Yes | `api/notifications/history`, AD-2/AD-4 |

No gap here. **Verdict: complete.**

## 2. FR Coverage (PRD FR-1 → FR-12)

| FR | Bound by an AD (by number)? | Homed via a CAP row? | Verdict |
|---|---|---|---|
| FR-1 | AD-8 | CAP-1 | OK |
| FR-2 | AD-8 | CAP-1 | OK |
| FR-3 | — | CAP-2 | OK (capability-level home only) |
| FR-4 | — | CAP-6 | OK (capability-level home only) |
| FR-5 | — | CAP-7 | OK (capability-level home only) |
| FR-6 | AD-2 | CAP-3 | OK |
| FR-7 | AD-2, AD-3 | CAP-3/CAP-4 | OK |
| FR-8 | — | CAP-4 | OK (capability-level home only; AD-2's "Binds" line cites CAP-4 but not FR-8 by number — minor citation gap, not a structural one) |
| FR-9 | AD-4 | CAP-5 | Homed, **but its most important consequence is not** — see Finding 1 |
| **FR-10** | **none** | **not referenced anywhere in the map** | **GAP — see Finding 1** |
| FR-11 | AD-3, AD-4 | CAP-8 | OK |
| FR-12 | AD-7 | separate cross-cutting row | Homed, **but incompletely** — see Finding 3 |

**FR-10 (Recipient Opt-In Consent Capture) is the one PRD functional requirement with no architectural home whatsoever** — not bound by any AD, not named in the Capability → Architecture Map (even the CAP-5 row, whose FRs per SPEC.md include opt-in via FR-9/FR-10, only cites AD-4/AD-7). Its only trace in the spine is the ERD's bare `USER ||--o{ OPT_IN_CONSENT : "consent history"` line — a shape with no governing rule attached.

---

## 3. High-Severity Findings

### Finding 1 — Opt-in/opt-out consent has an ERD box but zero governing rule (FR-10, and FR-9's phone-change consequence)

**Severity: High.**

FR-10 states two hard, testable rules:
- "A Recipient **cannot receive** Scheduled or Manual notifications until opt-in is recorded."
- "Opt-out is possible and **immediately stops future sends** to that Recipient."

FR-9 adds a third, explicitly tied to phone-number edits:
- "Changing a Recipient's phone number **requires fresh Opt-In Consent** before delivery resumes to the new number."

EXPERIENCE.md's UJ-3 flow depends on this last rule directly ("corrects the phone number in the Directory form (**triggering fresh Opt-In Consent** per FR-9's assumption)").

The spine's only artifact touching this is the ERD relationship `USER ||--o{ OPT_IN_CONSENT`. Nowhere does the spine say:
- that the recipient-resolution step AD-2 governs (which turns a target spec into `NotificationDelivery` rows) must **filter out any recipient without active opt-in consent** — this is a gating condition on the exact mechanism AD-2 is supposed to be the single source of truth for, and it's missing from AD-2's rule text entirely;
- that a phone-number edit on a `User` record must **invalidate/require re-creation of** the active `OPT_IN_CONSENT` row before that user re-enters the sendable set;
- what "opt-out... immediately stops future sends" means mechanically (does it soft-delete pending `NotificationDelivery` rows already queued for a not-yet-run scheduled send? does the scheduler re-check consent at fan-out time or at generation time?).

This is exactly the kind of quiet requirement an "Architecture Decision" list loses: it's a data-integrity/gating rule, not a new component, so it never became its own AD, but it directly modifies the behavior of AD-2 (Send Event resolution) and AD-4 (Recipient data ownership) as written. Recommend either a new AD-9 ("Opt-in gates recipient resolution") or folding an explicit clause into AD-2/AD-4.

### Finding 2 — No optimistic-concurrency mechanism for EXPERIENCE.md's mandatory "Conflict" edit state

**Severity: High.**

EXPERIENCE.md's State Patterns section states, as a flat requirement, not a nice-to-have:

> **Conflict** — editing a Recipient record that someone else just changed surfaces a conflict dialog showing both versions; it never silently overwrites.

This requires some form of optimistic concurrency control — a version counter, `updated_at`-based compare-and-swap, or ETag/If-Match — on writes to `Recipient`/`Team`/`RecipientList` (and presumably any other multi-admin-editable entity). The spine's Consistency Conventions table covers ids, timestamps, money formatting, and the error envelope shape (`{error:{code,message,details}}`), but never mentions a conflict/409 case or any versioning field, and none of AD-4/AD-7/AD-8 (the three ADs touching Recipient/Team writes) mention it either. Without this, "it never silently overwrites" is a UX promise the architecture doesn't back with a mechanism — the natural default implementation (last-write-wins on a bare UPDATE) is precisely the silent-overwrite behavior EXPERIENCE.md forbids.

### Finding 3 — AD-7's audit rule doesn't actually cover "login events," which FR-12 explicitly requires

**Severity: Medium-High.**

FR-12's consequences list, as a separate bullet from directory CRUD: **"Login events are recorded."** AD-7's rule text is precise and narrow:

> "Every service method that **mutates a Recipient, Team, RecipientList, opt-in/out state, or the Daily Report schedule** writes its data change and its `AuditLogEntry` in the same database transaction."

A login is not a mutation of any of those five things — it's an authentication event. Read literally, AD-7 (the spine's sole audit-coverage invariant) does not obligate anything to write an `AuditLogEntry` on login. This is a specific, checkable regression risk: a developer implementing strictly to AD-7's letter would correctly audit every directory change and never audit a single login, and nothing else in the spine catches the gap. Recommend widening AD-7's trigger list to explicitly include authentication events (successful and/or failed login), or adding a sentence acknowledging login as a sixth trigger.

### Finding 4 — HTTPS/TLS, an explicit SPEC.md Constraint and FR-1 consequence, is entirely absent from the spine

**Severity: Medium-High.**

SPEC.md's Constraints list: "All communication must be over HTTPS." FR-1's consequences: "All requests carrying credentials or session tokens occur over HTTPS only." PRD §8 Security NFR repeats it. AD-5 ("Deployment topology, environments, secrets") is the natural home — it already describes Nginx as the reverse proxy in front of the API and webhook endpoint — but never mentions TLS termination, certificate management, or an HTTP→HTTPS redirect/HSTS policy. Searched the full spine text for "HTTPS"/"TLS": zero occurrences. This is a named, testable security constraint that should be one clause in AD-5 (e.g., "Nginx terminates TLS; plain HTTP is redirected, never proxied") and currently isn't anywhere.

### Finding 5 — WhatsApp message templates have no architectural home, despite being a hard constraint on FR-8's entire mechanism

**Severity: Medium-High.**

EXPERIENCE.md's Notification composer spec is unambiguous that Manual Notifications are **not** free text:

> "Administrator picks a pre-approved WhatsApp template... and fills the template's variable slots... Free-form body text is **not** offered beyond what the chosen template's variables allow — this is a hard constraint from the messaging platform."

PRD §9 Cost reinforces this: every send (scheduled or manual) is "a billed template message under Meta's per-message pricing model," and "The WhatsApp template category (Utility vs. Marketing)... must be verified at WhatsApp Business Account setup."

AD-4 gets one glancing mention — `Notification`'s fields include "message/template" — but the spine never models: where approved template definitions live (a `MessageTemplate` entity? static config? synced from Meta's API?), how template-variable-slot validation happens before send, or how a template's approval-category (Utility/Marketing) is tracked and enforced. Given FR-8's plain-English phrasing ("compose a custom message") actively undersells this constraint, architecture — not just UX — needed to make the template concept a first-class citizen. It currently isn't in the ERD, the source tree, or any AD.

---

## 4. Medium-Severity Findings

### Finding 6 — Recipient-picker "live dedupe count" implies a side-effect-free preview capability the spine never allocates

EXPERIENCE.md's Recipient picker: selecting across mechanisms shows the de-duplicated count **live**, before Send is ever pressed — *"14 selected → 11 unique recipients (3 overlaps merged)."* AD-2's dedup rule ("resolves to one `NotificationDelivery` row before send, never after") is written entirely in terms of what happens **at send time**. Nothing in the spine allocates a stateless, repeatable "resolve target spec → unique recipient set" domain function that can be called on every picker interaction without creating any `NotificationDelivery` rows, nor a corresponding API endpoint (e.g., `POST /notifications/preview` or similar) for the compose UI to call. As written, a literal implementation of AD-2 alone would only let the frontend discover the dedup count by actually sending — the spine should either say the resolution logic is a pure function reused by both preview and commit paths, or note the preview endpoint explicitly.

### Finding 7 — Dashboard's "Data as of HH:MM" stale badge has no backing data-freshness concept

EXPERIENCE.md's State Patterns: "if the upstream Source System hasn't refreshed within its expected window, the Dashboard shows an explicit **'Data as of HH:MM'** badge rather than silently presenting old numbers as current." AD-6 (Source System ingestion contract: staging → validate → transform → upsert) never mentions tracking *when* the last successful ingestion run completed, nor an "expected refresh window" concept the API can compare against to decide staleness. There's no `IngestionRun`/`last_synced_at` concept anywhere in the ERD or Structural Seed. Without some persisted last-successful-sync timestamp, the Dashboard literally cannot render this badge. The same missing timestamp is also needed for EXPERIENCE.md's UJ-1 attachment flow ("optionally attaches the current performance report **with its generation date/period visible**") — both are instances of the same unmodeled concept.

### Finding 8 — Daily Report schedule time has no storage location, despite being audited and portal-editable

EXPERIENCE.md's IA table places "Daily Report global send-time (FR-6)" under Settings, editable by the Administrator; AD-7 explicitly lists "the Daily Report schedule" as one of the things whose mutation must be co-transactional with an audit write — implying it's a DB-backed, service-layer-mediated value, not an environment variable. But no `Settings`/`ScheduleConfig` entity appears anywhere in the ERD or Structural Seed, and the Deferred section treats "JWT session TTL" and "retry policy magnitude" as configurable-but-unmodeled, without doing the same for the schedule time. Recommend the ERD/entities note a minimal `Settings` (or equivalent) row so AD-7's audit obligation for schedule changes has somewhere concrete to attach to.

### Finding 9 — PRD Open Question #16 (resend path for exhausted retries) is not visibly closed

PRD OQ#16 asks explicitly: "What happens to a Recipient whose retries are exhausted within a Send Event — do they wait for the next scheduled run, or is there a manual-resend path?" FR-7's consequences state the recipient isn't auto-re-attempted until "the next scheduled run... or a fresh Administrator-triggered send" — which answers "no automatic retry beyond the window" but leaves open whether there's a **dedicated, targeted resend action** (e.g., a "Resend" button against one failed row in Notification History) versus the Administrator having to compose an entirely new Manual Notification aimed at just that one recipient. EXPERIENCE.md's UJ-3 flow resolves the delivery gap purely by fixing the phone number, not by describing a resend mechanic — so this may be implicitly decided as "no dedicated resend path," but the spine never states that as an architecture decision. Worth one explicit sentence either way (in AD-2's scope, or Deferred).

### Finding 10 — No architectural treatment of reliability/recovery NFRs (uptime, backup/restore)

SPEC.md Constraints and PRD §8 both state "99.5% uptime **with automatic recovery after failures**" as a Reliability NFR, and PRD §12 flags RTO/RPO as an explicit open question (OQ#10). AD-5, the deployment/topology AD ("Binds: all (operational envelope)"), covers container layout, environments, and secrets, but says nothing about Postgres backup/restore strategy, container restart policy, or any recovery mechanism at all. Given AD-5 is scoped exactly to "operational envelope," this NFR's complete absence — not even a "Deferred" acknowledgment — is a gap; retention (PRD OQ#9, Notification History/Audit Log/sales-data retention) has the identical problem: not addressed, not deferred, just absent.

### Finding 11 — Inconsistent treatment of two "business decision, not engineering call" items

The Deferred section explicitly defers "Brand top/low/focus ranking thresholds" as "a business decision per PRD FR-4's note, not an engineering call." The PRD's Assumptions Index flags Achievement %/Growth % formulas with the identical status (`[ASSUMPTION]`, "pending business/finance confirmation," PRD §3/§14) — yet the spine's Deferred list doesn't mention these formulas at all, leaving `domain/metrics` free to bake in an unstated formula with no flag that it's provisional, unlike the ranking-threshold case which got an explicit placeholder treatment.

---

## 5. Lower-Severity / Nitpick Findings

- **Phone-number uniqueness has no DB-level backing.** EXPERIENCE.md's Directory form "validates phone-number uniqueness inline (not just on submit)." AD-2 sets a precedent of enforcing invariants via "a database unique constraint... not application-level checking alone" for `NotificationDelivery`; the same treatment is never extended to `User.Mobile`, though the UX explicitly promises it as a hard rule, not just a UI nicety.
- **"Last Administrator cannot be deleted/deactivated" (FR-2) has no stated enforcement point.** AD-8 covers route-level auth-gate enforcement, not this specific business-rule guard (a service-level check in the Administrator-management flow). Not mentioned anywhere.
- **FR-3/FR-4/FR-5/FR-8 are homed via their CAP row but never cited by FR number in any AD's "Binds" line**, unlike FR-6/FR-7/FR-9/FR-11/FR-12. Purely a citation-completeness issue, not a structural gap — flagging for consistency only.
- **AD-2's "Binds" line names CAP-4 but not FR-8** even though CAP-4's entire content is FR-8 — same minor citation-completeness note as above.

---

## 6. Non-Goals Check

No violation found. Spot-checked against the spine:
- No per-recipient schedule customization is implied anywhere (consistent with FR-6's Out-of-Scope).
- Bulk CSV import is explicitly listed in Deferred, matching PRD OQ#14 / Non-Goals.
- `Doctor` is modeled as a flat reporting entity with **no relationship to the notification/recipient graph** (explicitly called out in the Structural Seed) — correctly keeps Doctors non-messageable, consistent with PRD §5's "Messaging doctors/HCPs directly... not currently planned for any phase."
- No interactive charting, image-rich messages, multi-language, or PDF/Excel export capability is implied by any AD or the source tree.
- Bangladesh PDPA residency is correctly treated as a non-architected, flagged legal item (AD-5, Deferred), matching PRD §10's explicit instruction not to make it a hard Phase 1 NFR.

## 7. PRD's 16 Open Questions — Traceability

| # | Topic | Addressed by spine? |
|---|---|---|
| 1 | Source System identity | Yes — correctly left open; only the ingestion *contract* (AD-6) is fixed, which is the right architectural response to an unresolved identity. |
| 2 | Recipient Group/Channel modeling | Yes — AD-4 (`RecipientList` with `kind` field). |
| 3 | Achievement %/Growth % formulas | No — not addressed, not deferred (see Finding 11). |
| 4 | Daily Report schedule time / global vs. per-recipient | Partial — AD-7 implies it's a mutable, audited value, but no storage location is modeled (see Finding 8). |
| 5 | Bangladesh PDPA residency | Yes — AD-5 + Deferred. |
| 6 | Production WhatsApp BSP | Yes — Deferred, isolated behind `ports/`. |
| 7 | Redis/Celery needed? | Yes — AD-2 + Deferred. |
| 8 | Team standalone / Notification split | Yes — AD-4. |
| 9 | Retention period (history/audit) | No — not addressed at all (see Finding 10). |
| 10 | Support/on-call, RTO/RPO | No — not addressed at all (see Finding 10). |
| 11 | JWT session TTL | Yes — Deferred, left configurable. |
| 12 | Retry policy (count, backoff) | Yes — Deferred, left configurable. |
| 13 | Org-scale figures | N/A — correctly not architecture's call, though it silently underwrites the AD-2 "no Redis/Celery" assumption without flagging that dependency explicitly. |
| 14 | Bulk import (CSV) | Yes — Deferred. |
| 15 | Budget ceiling | N/A — not an architecture concern. |
| 16 | Resend path for exhausted retries | No — not clearly closed (see Finding 9). |

**Net: 9 of 16 cleanly closed or correctly left open by design; 2 partially addressed; 4 silently unaddressed (#3, #9, #10, #16); 1 N/A.**
