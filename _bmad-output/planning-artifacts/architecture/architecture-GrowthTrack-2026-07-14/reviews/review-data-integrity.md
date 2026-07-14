---
name: 'Data Integrity Review — GrowthTrack Architecture Spine'
type: review
reviews: architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md
focus: 'zero-duplicate-sends, auditability, data-model integrity'
created: '2026-07-14'
---

# Data Integrity Review — GrowthTrack Architecture Spine

## Verdict

The spine's mechanisms are directed at the right problems, but on close reading none of the five areas is fully closed: the send-uniqueness rule (AD-2) protects against duplicate **rows**, not duplicate **Twilio API calls** against a single row surviving a crash — which is the actual failure mode SM-3 ("duplicate-send rate: target 0") most needs covered; the Team/RecipientList membership-resolution timing that FR-9 depends on is never pinned to creation-time vs. send-time; opt-in consent's phone-number-tied invalidation (an explicit PRD assumption) has no corresponding rule or field anywhere, only an unexplained ERD box; and deletion/lifecycle semantics for Recipient/Team/RecipientList are entirely unaddressed, despite FR-9 explicitly promising deletion and FR-11/FR-12 requiring permanent history. AD-7's co-transactionality claim is the one area that holds up structurally, with one small scope inconsistency against FR-12.

## Findings

### 1. [CRITICAL] AD-2 prevents duplicate rows, not duplicate sends against one row — the actual crash/race risk to SM-3 is unaddressed

AD-2's DB unique constraint on `(recipient_user_id, trigger_id, operational_day)` / `(recipient_user_id, notification_id)` guarantees at most one `NotificationDelivery` **row** exists per Send Event identity. That is sufficient to stop two independently-resolved recipient batches from creating duplicate bookkeeping. It does **not** stop the same existing row from being processed twice, which is the more likely real-world failure mode:

- A retry loop (or the original run) calls the Twilio adapter for a row whose status is `pending`/`failed`, the WhatsApp message goes out successfully, and the process crashes or is killed before the status/attempt-count update commits. On restart or on the next retry sweep, the row still reads `pending`/`failed` — nothing in AD-2/AD-3 stops it from being picked up and sent again. This is a classic dual-write/at-least-once gap, and it is precisely what SM-3 ("duplicate-send rate ... target: 0") and SM-C1 (silent-failure rate must stay at 0) are guarding against — a single row sent twice produces exactly one duplicate WhatsApp message with zero trace in the schema that it happened twice, since the constraint was never touched.
- The rule never states an atomic "claim" step (e.g., `UPDATE ... SET status='sending' WHERE status IN ('pending','failed') RETURNING id`, single winner proceeds to call Twilio) that would make the transition from "eligible to send" to "sending" itself race-safe. Without that, two concurrent workers (or the same process racing itself after a restart while an old thread is still mid-flight) can both read `pending`, both call Twilio, and both then attempt to update the same row.
- This gap is orthogonal to, and not fixed by, having "a database unique constraint on `NotificationDelivery`" — the constraint fires on `INSERT`, and retries/resends do not insert a new row (AD-4 states `NotificationDelivery` carries attempt count, implying updates to an existing row across retries).

**Recommendation:** Add an explicit rule that the transition from "eligible" to "in-flight" is a single atomic compare-and-swap on the row (row lock or conditional `UPDATE`), and that the Twilio call happens only after that CAS is won — never "insert-then-send unconditionally" or "read-then-send-then-update."

### 2. [HIGH] `trigger_id` is used in the uniqueness tuple but never defined — two builders (or the same builder across a crash) are not guaranteed to compute the same value

AD-2's identity tuple for Scheduled Notifications is `(recipient_user_id, trigger_id, operational_day)`. Nothing in the spine defines what `trigger_id` *is* — whether it is a deterministic value derived from the schedule configuration and the operational day (e.g., a stable string like `daily-report:2026-07-14`, recomputable identically by any process at any time), or an ephemeral value generated fresh each time APScheduler fires a job (e.g., a UUID tied to that particular execution/job-run instance).

This is not a cosmetic omission — it determines whether the uniqueness constraint does what AD-2 claims:

- If `trigger_id` is ephemeral (new value per firing), then a scheduler crash mid-run followed by a restart that re-fires the job (misfire handling, or a manual make-up run) generates a **new** `trigger_id`. Combined with the same `operational_day`, this does **not** collide with the original attempt's rows — the exact duplicate-send scenario the constraint exists to prevent would sail straight through it, because the tuple simply looks different the second time.
- If `trigger_id` is deterministic (derived purely from schedule config + operational day), it is largely redundant with `operational_day` in the same tuple — which is fine, but then the spine should say so, and should also address FR-6's default of "a single, global... schedule" vs. any future scenario where the same day could legitimately have more than one trigger (why else include both fields?).

The spine gives no formula, no generation point (created once and persisted at job-fire time vs. computed on the fly), and no statement of how it survives a scheduler restart. Per the review question, this is exactly the kind of value where two builders reading only this spine could reasonably implement it two different, incompatible ways — and either implementation choice interacts with Finding 1 to potentially defeat the whole mechanism.

**Recommendation:** State `trigger_id`'s derivation explicitly (e.g., "deterministic function of the schedule's configured time and the operational day, persisted the first time it is computed for that day, never regenerated") and state what happens across a scheduler restart mid-run.

### 3. [HIGH] Team/RecipientList membership-resolution timing (creation-time vs. send-time) is never pinned down, despite being load-bearing for FR-9

AD-4 separates `Notification` (target *spec*: Team/RecipientList/User references) from `NotificationDelivery` (one row per "resolved individual recipient"). AD-2 adds that a recipient reachable through more than one mechanism "resolves to one `NotificationDelivery` row before send, never after." This fixes the multi-mechanism de-dup question but leaves the more consequential question open: **when**, relative to a recurring Scheduled Notification's daily trigger, does Team/RecipientList membership get read?

Two structurally different implementations are both consistent with the spine's wording:

- **(a) Resolved fresh every operational day** at trigger time — a Team member added yesterday is included in today's run automatically.
- **(b) Resolved once**, at whatever point the `Notification` targeting a Team was configured, with membership effectively denormalized/cached from that moment — a Team member added afterward would never receive the recurring report until an admin re-touches the `Notification`.

FR-9 states as a testable consequence: "Adding, editing, or removing a recipient, group, channel, or team changes who future notifications (**scheduled and manual**) reach." This is a hard PRD guarantee, and it only holds under interpretation (a). The spine never says which interpretation is intended — AD-2's "before send, never after" resolves the *multi-mechanism* dedup ordering, but does not say resolution itself is re-run per operational day rather than cached from `Notification` creation. A builder implementing (b) would violate FR-9 while still satisfying every literal sentence in AD-2/AD-4.

**Recommendation:** Add an explicit sentence to AD-4 (or a new AD): "For Scheduled Notifications, Team/RecipientList membership is re-resolved fresh at each operational day's trigger — never cached from the time the Notification/schedule was configured." This single sentence would remove the ambiguity and make FR-9's guarantee mechanically true rather than incidentally true.

### 4. [HIGH] Opt-in consent's phone-number-tied invalidation (explicit PRD requirement) has no supporting rule, and consent is absent from the send pipeline entirely

Two distinct gaps here, both rooted in the same entity:

- **Structural gap.** The ERD introduces `OPT_IN_CONSENT` via `USER ||--o{ OPT_IN_CONSENT : "consent history"` — but the ERD's own stated scope is "only the relationships that were genuinely open (PRD Open Questions #2, #8)," and neither of those open questions is about consent. `OPT_IN_CONSENT` appears with no corresponding AD rule, no field list, and no explanation anywhere in the document. Meanwhile the PRD is explicit and specific: "Changing a Recipient's phone number requires fresh Opt-In Consent (FR-10) before delivery resumes to the new number `[ASSUMPTION: consent is tied to the number, not the person]`." A one-to-many "history" shape is *compatible* with that requirement (each record could carry the phone number it was captured against, with validity keyed to the User's *current* Mobile value) — but nothing in the spine states that this is how it works, versus the much simpler and equally-compatible-with-the-diagram alternative of a single overwritten consent flag on `User` that has no relationship to phone number at all. As drawn, the ERD is silent on which one it is, and the "tied to the number, not the person" invariant — explicitly called out as an assumption in the PRD — is not preserved anywhere in the architecture.
- **Pipeline gap.** FR-10 is a hard send gate: "A Recipient cannot receive Scheduled or Manual notifications until opt-in is recorded" and "Opt-out is possible and immediately stops future sends." Yet AD-2 (Send Event resolution/dedup) and AD-3 (delivery-status webhook) never mention a consent check as part of recipient resolution or send eligibility. As written, the architecture describes *how* a recipient becomes a `NotificationDelivery` row (dedup across targeting mechanisms) without ever stating that consent validity is a precondition of that resolution step. This is a silent path to sending to a non-consented or since-opted-out recipient.

**Recommendation:** Add an AD rule (or extend AD-4) that (1) defines `OPT_IN_CONSENT`'s minimum shape — at least a phone-number/value field and a validity window, so a Mobile change on `User` can be defined to invalidate the prior record — and (2) states explicitly that recipient resolution in AD-2 filters out recipients without current, valid consent before a `NotificationDelivery` row is created.

### 5. [HIGH] No deletion/lifecycle rule for Recipient/Team/RecipientList — real risk of either orphaned history or an undeleteable directory

FR-9 explicitly promises the Administrator can "remove" individual Users, Recipient Groups, Recipient Channels, and Sales Teams. The ERD ties `NotificationDelivery` to `USER` (`USER ||--o{ NOTIFICATION_DELIVERY : "receives"`) and `Notification` to `TEAM`/`RECIPIENT_LIST` (`targets`), and `SalesData` to `TEAM` (`aggregates`). FR-11/FR-12 require Notification History and the Audit Log to be permanent, queryable records ("system of record," append-only). The spine never states what happens to these references when a Recipient, Team, or RecipientList is removed:

- If removal is a hard `DELETE` with `ON DELETE CASCADE`, deleting a User destroys their entire `NotificationDelivery` history — directly undermining FR-11's "queryable log of every sent Notification" and SM-5's completeness target.
- If removal is a hard `DELETE` with `ON DELETE RESTRICT` (the FK-safe alternative), then any User, Team, or RecipientList that has ever been part of a send — which in practice is nearly everyone shortly after go-live — can **never** be deleted, breaking FR-9's promised capability outright.
- `entities.md`'s source `User` entity already carries a `Status` field (`UserID, Name, Mobile, Role, Status`), which strongly suggests the intended resolution is soft-delete/deactivation rather than hard delete — but the spine never states this as an architectural rule, never extends the same pattern to `Team`/`RecipientList`, and never says how a "removed" Recipient/Team/RecipientList is excluded from future targeting resolution (Finding 3) while its historical rows remain intact and attributable.

**Recommendation:** Add an explicit rule: removal of a Recipient, Team, or RecipientList is always a soft-delete/deactivation (status flag), never a hard delete; historical `NotificationDelivery`/`AuditLogEntry` rows retain their foreign keys permanently; deactivated entities are excluded from future targeting resolution (ties directly into Finding 3's resolution-timing rule) but never removed from the schema.

### 6. [LOW-MEDIUM] AD-7 co-transactionality is structurally achievable given the topology, but has a scope gap against FR-12 and rests on an unstated assumption

Checking whether AD-7's claim is achievable: yes, for what it actually covers. All of the mutations AD-7 lists (Recipient, Team, RecipientList, opt-in/out, Daily Report schedule) are Administrator-driven CRUD that live entirely inside the single `api/` FastAPI process against the single Postgres database (per the deployment topology and Capability Map — CAP-5 lives in `api/recipients` + `domain/recipients`). A single SQLAlchemy session/transaction wrapping both the entity write and the `AuditLogEntry` insert is genuinely one physical transaction here — there is no cross-service or cross-process boundary for this specific scope, so the concern about the webhook handler and audit log living in "different services" doesn't actually apply: the webhook handler (`AD-3`) writes `NotificationDelivery` status, which AD-7 doesn't claim needs co-transactional audit logging at all (delivery-status updates aren't in AD-7's mutation list, and correctly so — they're system-driven facts, not administrative actions).

Two smaller issues worth fixing:

- **Scope inconsistency with FR-12.** FR-12 explicitly requires "Login events are recorded" as part of the Audit Log. AD-7's rule text lists only "a Recipient, Team, RecipientList, opt-in/out state, or the Daily Report schedule" as triggering co-transactional audit writes — login events are not in that list. Either this is an oversight (login events should be added to AD-7's rule) or login-event audit logging is meant to follow a different, unstated mechanism. As written, there's a literal gap between what FR-12 promises and what AD-7 guarantees.
- **Unstated dependency.** AD-7's guarantee is only true *because* all covered mutations currently happen in one process against one database. Nothing in the spine flags this as a load-bearing assumption that must be preserved if the architecture evolves (e.g., an async bulk-import path, mentioned as a Phase-2-ish deferred item, or splitting recipient management into its own service later) — a future change could silently break the co-transactionality guarantee without tripping any stated invariant, since the invariant is written as if it's structural rather than an artifact of the current monolith.

**Recommendation:** Add "Login events" to AD-7's mutation list to match FR-12 verbatim, and add a note flagging single-process/single-DB as the reason the guarantee holds, so future changes that break that assumption are forced to re-examine AD-7.

## Summary Table

| # | Severity | Area | One-line issue |
|---|----------|------|-----------------|
| 1 | Critical | AD-2 | Unique constraint stops duplicate rows, not a crashed/racing retry re-sending via Twilio against one existing row — the actual mechanism SM-3 needs is an atomic claim/CAS step, which is absent. |
| 2 | High | AD-2 | `trigger_id` is used in the uniqueness key but its derivation (deterministic vs. ephemeral-per-firing) is never defined, so a scheduler restart could produce a non-colliding tuple for what should be the same Send Event. |
| 3 | High | AD-4 | Team/RecipientList resolution timing (creation-time vs. per-operational-day at send-time) is never fixed, though FR-9 requires membership changes to reach future scheduled sends. |
| 4 | High | ERD / AD-4 | `OPT_IN_CONSENT` appears in the ERD with no defined shape and no stated invariant tying validity to the current phone number; consent is also never referenced as a precondition in the AD-2 send/resolution pipeline. |
| 5 | High | ERD / AD-4 | No deletion/lifecycle rule for Recipient/Team/RecipientList; hard delete would either cascade-destroy audit/history or (via FK restrict) make FR-9's promised deletion capability impossible. `User.Status` in entities.md hints at the intended soft-delete fix but it's never stated as an architectural rule. |
| 6 | Low-Medium | AD-7 | Co-transactionality is achievable given the single-process/single-DB topology, but the rule text omits "Login events" (required by FR-12) and doesn't flag single-process-ness as the load-bearing assumption behind the guarantee. |
