---
name: 'Adversarial Divergence Review — GrowthTrack Architecture Spine'
type: review
reviews: ../ARCHITECTURE-SPINE.md
lens: 'two compliant builders, structurally incompatible output'
created: '2026-07-14'
---

# Adversarial Divergence Review — ARCHITECTURE-SPINE.md

## Method

For each AD and Consistency Convention, I tried to construct two builders — each implementing a different Phase 1 epic, each reading only the spine (plus its named upstream sources) as their contract — who each satisfy the rule's literal text but produce code, schemas, or runtime behavior that collide when integrated. I cross-checked every claimed gap against `SPEC.md`, `entities.md`, `prd.md`, and the architecture `.memlog.md` to make sure I wasn't "finding" something already resolved upstream. Where a term (e.g. `trigger_id`) appears nowhere except the spine itself, that is noted explicitly — it means the ambiguity is the spine's own invention, not an inherited one.

## Verdict

The spine is well-constructed at the level of *naming the right seams* (ports/adapters, Send Event identity, webhook-as-sole-writer, entity split) but under-specifies the seams' **exact mechanics** at precisely the points where two builders would need to agree byte-for-byte to avoid collision. Four of the findings below (F1, F2, F3, F5) are load-bearing: each maps directly onto a stated hard constraint (SM-3 zero-duplicate-sends, FR-11 unified history) that the spine's own "Prevents" clauses claim to guarantee, and each has at least one legal reading that violates it.

---

## F1 — `trigger_id` is undefined; two legal readings produce opposite dedup outcomes on scheduler restart

**Severity: Critical.** Directly threatens SM-3 (zero duplicate sends), the exact thing AD-2 exists to prevent.

AD-2's Rule: *"A Send Event's identity is `(recipient_user_id, trigger_id, operational_day)` for Scheduled Notifications... enforced by a database unique constraint."* `trigger_id` is never defined — not in the spine, not in `entities.md`, not in `SPEC.md`/`prd.md`, not in the architecture `.memlog.md` (checked all four; the term first appears in the memlog's own AD draft with no elaboration). It is a spine-invented primitive doing load-bearing work with zero specification of what value populates it.

Two builders, both reading only AD-2's text, can each honestly conclude:

- **Builder A** reads `trigger_id` as *"the identifier of the schedule definition that is firing"* — e.g. a stable string like `"daily_sales_report"`, constant across every day and every run. Under this reading, if the scheduler crashes mid-fan-out and APScheduler re-fires (or is manually restarted and catches up) the same day's job, the second run computes the *same* `(recipient_user_id, "daily_sales_report", operational_day)` tuple per recipient — the DB unique constraint correctly rejects the re-insert as a duplicate, and only the still-unsent recipients get new rows. This is the interpretation that makes AD-2's stated guarantee true.
- **Builder B** reads `trigger_id` as *"the identifier of this specific invocation/trigger event"* — the natural reading if you come from an event-sourcing background, where a "trigger" is a discrete occurrence, not a category. Under this reading, `trigger_id` is minted fresh (e.g. a UUID) every time the job fires. A restart-and-refire mid-run mints a *new* `trigger_id`, so the retry's tuple never collides with the first run's rows — every recipient who already received a message on the aborted run gets a **second, genuinely duplicate** message on the resumed run. This builder has still satisfied AD-2's literal text (identity tuple present, DB unique constraint present) while directly producing the duplicate-send SM-3 exists to make zero.

Both builders can point to the same sentence as their justification. Neither is wrong about what the sentence says — the sentence just doesn't say enough.

A secondary, compounding ambiguity: **when** is `operational_day` computed for a given row — once, when the scheduler job starts (captured in job context and threaded through the whole fan-out), or freshly per-row/per-recipient at insert time? If a crash-and-resume straddles local midnight (Asia/Dhaka), a per-row computation gives resumed rows a *different* `operational_day` than the aborted run's rows, which defeats the unique constraint's collision-detection regardless of which `trigger_id` reading is used, because `operational_day` — not just `trigger_id` — is part of the same tuple.

**Fix direction:** AD-2 needs to state explicitly: (a) `trigger_id` = the stable identifier of the *schedule definition*, not the invocation, with an example; (b) `operational_day` and `trigger_id` are both computed once per job *run* (captured at job-start) and passed unchanged into every row's insert for that run, never recomputed per recipient; (c) an explicit statement that scheduler restart-and-resume is expected to hit unique-constraint conflicts on already-sent recipients and must treat that as success, not error.

---

## F2 — "a database unique constraint" doesn't specify partial indexes; the naive reading silently defeats manual-notification dedup via Postgres NULL semantics

**Severity: Critical.** A second, independent path to the same SM-3 violation, on the *manual* side this time.

AD-2 gives two different identity tuples for the same table: `(recipient_user_id, trigger_id, operational_day)` for Scheduled, `(recipient_user_id, notification_id)` for Manual. For both tuples to live on one `NotificationDelivery` table, `trigger_id`/`operational_day` must be nullable for Manual rows and `notification_id` must be nullable for Scheduled rows (or some `type` discriminator must be involved). AD-2 says only "enforced by a database unique constraint" — singular, unqualified.

- **Builder A** implements this as one composite constraint: `UNIQUE (recipient_user_id, trigger_id, operational_day, notification_id)` across all four columns, with the "other type's" columns left NULL per row. This satisfies "a database unique constraint on NotificationDelivery" to the letter. It is also **broken**: PostgreSQL (like standard SQL) treats NULL as distinct from every other NULL for uniqueness purposes, so two Manual rows for the same recipient and same `notification_id`, both with NULL `trigger_id`/`operational_day`, do **not** collide — the constraint silently permits duplicate Manual-notification deliveries, exactly the case SM-3 forbids. Nothing in the app layer catches this because AD-2 explicitly says the DB constraint is the enforcement mechanism, "not application-level checking alone" — which this builder read as license to skip app-level double-checking.
- **Builder B**, aware of the NULL-uniqueness gotcha, instead creates two **partial unique indexes** — `UNIQUE (recipient_user_id, trigger_id, operational_day) WHERE notification_type = 'scheduled'` and `UNIQUE (recipient_user_id, notification_id) WHERE notification_type = 'manual'` — which correctly enforces both tuples independently.

Both builders can claim literal compliance with "enforced by a database unique constraint, not application-level checking alone." Only one of them actually has zero-duplicate-sends. This is exactly the kind of "each individually legal, structurally incompatible" defect the spine needs to foreclose, and it's foreclosable with one added sentence naming the mechanism (partial/filtered unique indexes) rather than leaving "a unique constraint" underspecified.

**Fix direction:** AD-2 should name the mechanism: two partial unique indexes keyed by a `notification_type`/discriminator column, not one composite constraint over nullable columns. This is a one-line addition that closes a real correctness hole.

---

## F3 — Retry reuses the same Send Event (per PRD glossary), but nothing says what happens to `provider_message_sid` on retry — a genuine two-writer race between AD-2's retry orchestration and AD-3's webhook

**Severity: High.**

The PRD glossary is explicit: *"Send Event — ...A retry of a failed attempt is part of the same Send Event, not a new one."* So a retried attempt updates the **same** `NotificationDelivery` row (AD-2's retry orchestration), and AD-3 says `NotificationDelivery` "stores the provider message SID returned at send time — the webhook's sole correlation key back to the right delivery row." AD-4 lists the row's fields as "status, attempt count, failure reason" — no mention of the SID's cardinality, and no mention of what a *second* send attempt does to a *first* attempt's already-stored SID.

Concretely: attempt #1's Twilio API call times out client-side before GrowthTrack ever receives (or persists) attempt #1's SID — from the domain's point of view, the send *appears* to have failed with no SID captured, so retry orchestration (AD-2) marks the row for retry and, on attempt #2, invokes send again and writes attempt #2's SID into the row (or, if a builder implements it as overwrite, clobbers whatever was there). Two things can now go wrong, and they diverge by builder:

- **Builder A** stores a single `provider_message_sid` column, overwritten on every attempt. If attempt #1's send actually *did* reach Twilio despite the client-side timeout (Twilio dispatched the message; only the synchronous HTTP response was lost), Twilio's webhook callback for **attempt #1's SID** arrives at some point — but by then the row's SID column has already been overwritten to attempt #2's value. AD-3's lookup-by-SID either finds no match (silently dropped, permanently untracked status for a message that really was delivered) or, worse in a system using UUID SIDs this is unlikely to collide with a wrong row, but the correlation is simply lost. Meanwhile attempt #2 was a genuine second WhatsApp message sent to the recipient — a real duplicate, delivered outside AD-2's tuple-based dedup entirely, because retry-of-an-existing-row was never subject to the insert-time unique constraint in the first place.
- **Builder B**, recognizing multiple attempts need multiple SIDs, stores per-attempt SIDs (e.g. a small `notification_delivery_attempt` side table, or an array column) so every webhook callback for every historical SID still correlates. This is a materially different schema and a materially different webhook-lookup query than Builder A's.

Both builders are individually compliant with AD-2 ("retry is part of the same Send Event, updates the same row"), AD-3 ("stores the provider message SID... the webhook's sole correlation key"), and AD-4 ("attempt count" as a field) — none of the three ADs says whether the SID is 1:1-current or 1:many-historical, and none addresses the write-ordering race between "retry orchestration writes a new SID + resets status for the new attempt" and "webhook writes status for an older, in-flight attempt's SID arriving late." This is also, functionally, a second writer of `NotificationDelivery.status`/`provider_message_sid` beyond the webhook that AD-3 declares to be the sole post-send status writer — AD-3's "sole writer" claim is only true if retry orchestration's writes are cleanly partitioned (by time, or by an explicit state machine) from the webhook's writes, and nothing enforces that partition.

**Fix direction:** AD-3 (or AD-2) needs to state explicitly whether SIDs are per-attempt (recommend: yes, via an attempts sub-table or SID history), and needs a stated rule for what "sole writer of post-send delivery status" means when a retry is in flight for the same row a stale webhook callback references — e.g., "a webhook callback for a SID that is not the row's *current* attempt's SID is discarded/logged, never applied."

---

## F4 — Manual-notification "resend" is an explicitly open PRD question; AD-2's identity tuple silently presupposes an answer

**Severity: High.**

PRD Open Question #16 (unresolved, by the PRD's own admission): *"What happens to a Recipient whose retries are exhausted within a Send Event — do they wait for the next scheduled run, or is there a manual-resend path?"* The spine's Deferred section punts "exact retry policy magnitude" but says nothing about resend, and AD-2 fixes Manual identity as `(recipient_user_id, notification_id)` without ever engaging with what a UI-level "resend" action does to that tuple.

- **Builder A** (implementing CAP-4's admin-facing "retry failed sends" affordance) treats resend as *"compose and send again"* — a brand-new `Notification` row with a fresh `notification_id`, hence a fresh, non-colliding identity tuple, hence a fresh set of `NotificationDelivery` rows. Fully AD-2 compliant. Consequence: Notification History (CAP-8/FR-11) now shows two (or more) separate `Notification` entries for what an admin perceives and describes as "one notification, retried" — inflating history, and breaking any "attempt count" narrative that assumed attempts live under one row.
- **Builder B** treats resend as *"retry the existing Send Event"* — reusing the existing `notification_id`, re-invoking send for the previously-failed `NotificationDelivery` rows only, incrementing their `attempt_count` in place. Also AD-2 compliant (same tuple, no new insert — an UPDATE path, not subject to the unique constraint at all). Consequence: no new `Notification` row, history shows one entry whose per-recipient status timeline extends.

Whichever epic/engineer resolves Open Q16 first bakes in one of these two semantics; the other, unaware, builds CAP-8's history view or CAP-4's compose UI against the other assumption. Neither violates AD-2's letter. The spine should not leave a PRD-flagged open question this structurally consequential to be silently resolved by whoever gets to CAP-4 first.

**Fix direction:** Either resolve Open Q16 in the spine (recommended: resend reuses `notification_id`/updates existing rows, matching the PRD glossary's "retry is part of the same Send Event" framing) or explicitly flag it in Deferred with a note that CAP-4 and CAP-8 builders must not proceed independently until it's decided.

---

## F5 — `Notification`'s "target spec" has no fixed persistence shape; relational joins vs. a JSON blob both satisfy AD-4's letter, and CAP-8 breaks under one of them

**Severity: High.** This is the "two different ways of representing which recipients a Notification targets" scenario named directly in the review brief.

AD-4's Rule states `Notification` is "the request/definition: type, message/template, target spec, creator" and the ERD shows `NOTIFICATION }o--o{ USER`, `}o--o{ TEAM`, `}o--o{ RECIPIENT_LIST` as three many-to-many relationships. But the ERD is explicitly scoped ("Only the relationships that were genuinely open... are fixed here — full field lists remain owned by entities.md and, once code exists, the code itself") and AD-4's prose never states *how* "target spec" must be persisted. `entities.md`'s source `Notification` entity had only a flat `Recipient` field — the three-way many-to-many split is entirely the spine's own invention, introduced with no accompanying statement that it must be relational.

- **Builder A** (building CAP-4's compose UI, which lets an admin freely combine individuals + Teams + RecipientLists in one send) implements `target_spec` as a single JSON column — `{"user_ids": [...], "team_ids": [...], "recipient_list_ids": [...]}` — because the UI's multi-select-of-three-kinds maps naturally onto one blob, and nothing in AD-4 forbids it.
- **Builder B** (building CAP-8's history view, or CAP-5's "who does this Team/RecipientList currently feed into") reads the ERD literally and expects real join tables (`notification_targets_user`, `notification_targets_team`, `notification_targets_recipient_list`) so that "show me every Notification that targeted Team X" is a normal SQL join, not a JSON containment query layered on top of an assumption about the blob's internal key names.

Both builders are compliant with AD-4's text (it names entities and relationships, never a storage mechanism). The resulting schema/query-layer mismatch is discovered only at integration, and if CAP-4 ships first with the JSON shape, CAP-8's "filterable by recipient... message type" (FR-11) and any Recipient-directory-side "what will removing this RecipientList affect" query become materially harder or impossible without a migration.

A second, related ambiguity buried in the same AD: does `target_spec` persist the **original targeting intent** (e.g., "Team Sales-North" as a named target, permanently, for display) or only the **resolved individual-recipient set** (with the Team/RecipientList reference optional/decorative)? A CAP-3 (scheduled) builder, whose sends are an implicit broadcast-to-all-active-recipients with no admin-composed target selection, may reasonably create `Notification` rows with an *empty* target-spec (no Team/RecipientList/User rows at all — "broadcast" is implicit), while CAP-8 assumes every `Notification` row has a populated target spec it can render. This is the same shape-of-data-ownership question as above, just surfaced from the scheduled side.

**Fix direction:** AD-4 should pin the persistence shape explicitly (recommend: relational join tables, matching the ERD, since it's the only shape that supports FR-11's filtering and CAP-5's impact-analysis needs), and should state what a Scheduled Notification's target spec looks like (even if it's "no rows — Scheduled implies broadcast to all active, opted-in Recipients, a fact encoded by `type = 'scheduled'`, not by populated target rows").

---

## F6 — AD-2's scheduled-tuple design and AD-4's ERD cardinality quietly disagree about whether `notification_id` is ever NULL

**Severity: Medium-High.**

AD-2's Scheduled identity tuple is `(recipient_user_id, trigger_id, operational_day)` — it does not include `notification_id` at all. This invites a natural reading (reinforced by F5's observation that Scheduled sends may have no admin-composed target spec) that Scheduled `NotificationDelivery` rows might not need a `Notification` parent at all, or that `notification_id` is nullable for them. AD-4's ERD, however, draws `NOTIFICATION ||--o{ NOTIFICATION_DELIVERY : "resolves to"` — `||` is exactly-one, mandatory cardinality on the Notification side; every `NotificationDelivery` row is drawn as requiring exactly one parent `Notification`.

- A **CAP-3 builder**, working primarily from AD-2's tuple (which never mentions `notification_id`) and the fan-out mechanics, may treat the `Notification` parent as optional for Scheduled rows, or invent an ad hoc "one shared Notification row reused for every day's report" (violating "operational_day" as a per-run concept) to avoid dealing with FK-not-null constraints they don't see motivated.
- A **CAP-8 builder**, working from AD-4's ERD (mandatory FK), assumes every row joins cleanly to a `Notification` and writes a history query with an inner join, which will silently drop or error on any Scheduled row that doesn't have one.

Both are defensible readings of their respective governing AD. The spine should state explicitly that a `Notification` row is created per scheduled run too (system-authored, `creator = NULL`/a system sentinel, `type = 'scheduled'`) so the FK is never optional and both builders converge on the same answer.

**Fix direction:** One sentence in AD-2 or AD-4: "Every scheduled run creates exactly one `Notification` row (creator = system) before fan-out; `notification_id` is never NULL on `NotificationDelivery`, for either Notification type."

---

## F7 — AD-1 legally permits a second, domain-bypassing write path to `NotificationDelivery`; the Consistency Convention's "route handlers never touch a repository directly" rule doesn't cover it

**Severity: Medium-High.** This is the "ports/adapters boundary ambiguity" the review brief asks about directly.

AD-1's Rule: *"`api/`, `scheduler/`, and every `adapters/*` package may import `domain/` and `ports/`, never each other."* Read literally, `api/` is explicitly permitted to import `ports/` **directly**, with no requirement to route through `domain/`. The Consistency Convention narrows "no route handler touches a repository directly" to a named list — *"Recipient/Team/Notification/User"* — and `NotificationDelivery` is conspicuously absent from that list.

Put those two facts together: the webhook handler (`POST /webhooks/twilio/status`, living in `api/` per the source tree) is free, under a fully literal reading of both AD-1 and the Consistency Convention, to call a `NotificationDeliveryRepository` port directly to write `status`, with **no domain service in between** — since (a) `api/` importing `ports/` is explicitly allowed, and (b) `NotificationDelivery` isn't one of the four entities the "goes through domain service layer" convention names.

- **Builder A** (webhook handler) does exactly this — signature-verify, look up by SID, `repo.update_status(...)` directly against the persistence port. Fast, simple, and fully rule-compliant.
- **Builder B** (CAP-3/CAP-4 send + retry orchestration) puts every `NotificationDelivery` mutation through a `domain/notifications` service method, because that's the only sane place to enforce e.g. a status-transition guard (no regressing `delivered` back to `sent` on a late/duplicate webhook — see F10) or to keep attempt-count/failure-reason logic in one place.

The result: the single row `NotificationDelivery` has two structurally different write paths into the same columns — one funneled through domain business rules, one bypassing them entirely straight from `api/` to `ports/`. Any invariant Builder B's domain service enforces (ordering, idempotency-of-status-application, audit-adjacent side effects) simply does not exist on Builder A's path, and nothing in AD-1 or the Consistency Convention forces them to converge, because the literal rules were written before `NotificationDelivery` existed as a concept the "domain service layer" convention needed to enumerate.

**Fix direction:** Add `NotificationDelivery` explicitly to the "all writes go through the domain service layer" convention, and have AD-3 state that the webhook handler calls a `domain/notifications` status-update method (not a repository port directly) — closing the AD-1 loophole the same stroke that closes the missing-entity gap in the convention.

---

## F8 — AD-1's signature-type checklist polices imports, not knowledge coupling; provider-specific logic can legally live in `domain/`

**Severity: Medium.**

AD-1's enforceable checklist is narrow and mechanical: *"No Twilio SDK type, no Source-System-specific type, and no SQLAlchemy model may appear in a `domain/` function signature."* This is a real, checkable rule — and it is silent on **business logic that encodes a specific provider's behavior using only primitive types**, which passes every literal check while defeating AD-1's own stated purpose ("Prevents: domain/business logic quietly coupling to Twilio... the exact coupling that would make the named provider swaps... a one-adapter change").

Concretely: "retry orchestration" is explicitly named as a `domain/` responsibility (design-paradigm section, and AD-2's Rule). Retry orchestration needs to decide which send failures are retryable (rate-limited, transient network) versus permanent (invalid number, recipient opted out at the carrier level) — and Twilio surfaces this distinction via specific numeric error codes (e.g. its `63016`/`21211`-style code space). A builder implementing `domain/notifications/retry.py::classify_failure(error_code: str) -> RetryDecision` with an internal mapping table keyed on Twilio's actual error code values has introduced **zero** forbidden types (no SDK import, `error_code` is a plain `str`) — fully AD-1 compliant by the letter — while making `domain/` silently unusable against any future WhatsApp BSP (360dialog/Gupshup) whose error-code space differs, exactly the swap AD-1's Deferred section names as the reason this paradigm was chosen. A second builder, more careful, defines the classification as a `ports/`-level contract (`WhatsAppSender` returns a provider-agnostic `SendOutcome{retryable: bool, ...}` enum, with the Twilio-code-to-outcome mapping living in `adapters/whatsapp_twilio/`) — also AD-1 compliant, and actually swap-safe. Both builders pass every stated check; only one preserves the property AD-1 exists to guarantee. Because this is a knowledge-coupling problem, not an import-graph problem, no amount of import-linting catches the divergence — it has to be closed by convention/example, not by AD-1's current checklist alone.

**Fix direction:** Add one explicit sentence/example to AD-1 (or a short note in the port contract for `WhatsAppSender`): outcome/error classification crosses the port as an already-normalized, provider-agnostic value; provider-specific code/string mappings live only in the adapter, never in `domain/`, even when no forbidden type appears in the signature.

---

## F9 — RecipientList membership: static snapshot vs. Team-derived dynamic list is unaddressed

**Severity: Medium.**

AD-4 fixes `RecipientList` as the single entity unifying Recipient Group/Channel, and the ERD shows only `USER }o--o{ RECIPIENT_LIST : "member of"` — a direct User-to-List join, with `Team` drawn as a separate, unconnected entity (`TEAM ||--o{ USER : "has members"`). Nothing in AD-4 states whether a `RecipientList` of `kind = Channel` (or Group) can be *defined as* "current members of Team X" (dynamically resolved at fan-out time) versus being an always-static, independently-curated set of User rows that merely happened to be seeded from a Team roster once.

- **Builder A** (CAP-5, directory management) implements `RecipientList` exactly as the ERD draws it: a plain many-to-many join to `User`, no `team_id` anywhere. An admin who wants a Channel to track a Team's membership must manually re-sync it whenever the Team's roster changes — a real operational gap the UX docs don't call out, but structurally consistent with the ERD.
- **Builder B** (CAP-4, targeting/fan-out, or a different CAP-5 sub-feature), reading "same fan-out-to-individual-numbers mechanism" as license for convenience, adds an optional `team_id` FK to `RecipientList` so a Channel can be *derived* from a Team live, resolving members at send time rather than at list-edit time.

Neither reading contradicts AD-4's stated text (it never says "no FK to Team," only that Team is "a standalone entity, not a field" — which is about `User.team`, not about `RecipientList`). The two schemas are incompatible: CAP-5's admin UI (which shows/edits List membership) behaves completely differently depending on which model is live, and CAP-8/CAP-4's targeting-resolution logic (F5's "target spec") would need to know which kind of List it's fanning out, which the spine doesn't specify.

**Fix direction:** One sentence: "RecipientList membership is always a static, explicitly-curated set of User rows; a List is never dynamically derived from Team membership, even if originally seeded from one."

---

## F10 — Webhook status writes have no stated ordering/idempotency rule; duplicate or out-of-order Twilio callbacks can regress status

**Severity: Medium.**

AD-3 states the webhook is "the only writer of post-send delivery status" and must verify the signature — nothing else. It does not state: (a) what happens if the same status callback arrives twice (Twilio, like most webhook providers, is at-least-once, not exactly-once), or (b) what happens if callbacks arrive out of order (a delayed `sent` callback arriving after a later `delivered` callback already updated the row).

- **Builder A** implements the handler as an unconditional overwrite: `row.status = payload.status`. Simple, satisfies "the only writer," but a late/duplicate/out-of-order callback can visibly regress a delivery from `delivered` back to `sent` (or from a terminal `failed` back to a non-terminal state) in Notification History (CAP-8/FR-11), which is exactly the kind of thing SM-5 ("history/audit completeness... 100%... accurate status") would flag as a defect.
- **Builder B** implements a forward-only state-machine guard (`queued < sent < delivered < read`, `failed` terminal), rejecting any callback that would move status backward.

Both satisfy AD-3's text; only one is safe under Twilio's actual at-least-once, no-ordering-guarantee delivery semantics for webhooks. Because CAP-3 and CAP-4 both funnel through this one endpoint (by AD-3's own design), whichever behavior the first builder ships becomes the de facto contract for every notification in the system — worth pinning down explicitly rather than leaving to whoever writes the handler first.

**Fix direction:** AD-3 should state the status values form a monotonic sequence and specify that the handler applies a callback only if it advances (or is idempotently equal to) the row's current status, never regresses it.

---

## F11 — Webhook-arrives-before-row-exists race has no stated fallback

**Severity: Medium.**

If the Twilio status callback for a just-dispatched message reaches `/webhooks/twilio/status` before the local transaction that persists that message's `provider_message_sid` onto its `NotificationDelivery` row has committed (plausible under load, or with a slow local DB write racing a fast provider callback), AD-3's "sole correlation key" lookup finds no row. AD-3 doesn't say what the handler does next.

- **Builder A** returns a 404/500, relying on Twilio's own webhook retry-with-backoff to eventually succeed once the row exists.
- **Builder B**, worried about losing the callback if Twilio's retry budget is exhausted before the row commits, buffers/persists the orphaned callback (e.g. an `unmatched_webhook_event` staging row keyed by SID) for later reconciliation once the SID appears.

Both are "reasonable" and neither violates AD-3's text, but they produce different failure surfaces (silent data loss on Twilio retry exhaustion vs. an entirely separate reconciliation subsystem nothing else in the spine anticipates or accounts for in the source tree/ERD).

**Fix direction:** State the expected behavior explicitly — recommend requiring the send-path transaction to commit the `provider_message_sid` before the send call is considered complete (i.e., no window where Twilio could plausibly call back before the SID is persisted, since the SID is only known *after* Twilio's synchronous API response, which is also when the row should be written) — and additionally specify the 404-and-rely-on-Twilio's-retry behavior as the deliberate fallback, so no one builds a reconciliation subsystem unprompted.

---

## F12 — `ports/` has no stated ownership/change-control rule

**Severity: Low-Medium.** Structural governance gap rather than a concrete collision, but worth flagging.

AD-1 says `domain/` may import only `ports/`, and every inbound/outbound adapter may import `ports/` too — but nothing in the spine says who may *add to or change* a port interface once more than one epic depends on it. `NotificationRepository`/`WhatsAppSender`-style ports are exactly the kind of shared surface two independently-built epics (CAP-3 scheduled sends, CAP-4 manual sends) both need, and both CAP-3 and CAP-4's builders are individually authorized by AD-1 to depend on and, implicitly, to extend these ports. Without a stated single-owner or additive-only-with-review convention, two builders can each add incompatible or overlapping methods to the same port interface (e.g. one adds `mark_delivered(delivery_id, sid)`, the other independently adds `update_status(delivery_id, status, sid)` covering the same need) with no rule telling either of them the other's change exists or which one is canonical.

**Fix direction:** Not necessarily a new AD — a one-line convention ("`ports/` interfaces are additive-only; a new method requires checking whether an existing port method already covers the need") would close most of the risk cheaply.

---

## Summary table

| # | Finding | Severity | AD(s) implicated |
|---|---|---|---|
| F1 | `trigger_id` undefined — stable-per-schedule vs fresh-per-invocation | Critical | AD-2 |
| F2 | Composite nullable unique constraint vs. partial indexes — NULL semantics defeat manual dedup | Critical | AD-2 |
| F3 | Retry reuses Send Event; SID overwrite + webhook correlation race | High | AD-2, AD-3, AD-4 |
| F4 | Manual "resend" semantics — new Notification vs. reuse existing (PRD Open Q16 unresolved) | High | AD-2 |
| F5 | Notification "target spec" shape — relational joins vs. JSON blob | High | AD-4 |
| F6 | Scheduled tuple omits notification_id vs. ERD's mandatory FK cardinality | Medium-High | AD-2, AD-4 |
| F7 | AD-1 + Consistency Convention gap lets webhook bypass domain/ for NotificationDelivery writes | Medium-High | AD-1, Consistency Conventions |
| F8 | AD-1's type-signature checklist doesn't stop provider-specific knowledge coupling in domain/ | Medium | AD-1 |
| F9 | RecipientList: static snapshot vs. Team-derived dynamic membership | Medium | AD-4 |
| F10 | Webhook status writes: no ordering/idempotency/monotonicity rule | Medium | AD-3 |
| F11 | Webhook-arrives-before-row-exists race has no stated fallback | Medium | AD-3 |
| F12 | `ports/` has no ownership/change-control convention | Low-Medium | AD-1 |
