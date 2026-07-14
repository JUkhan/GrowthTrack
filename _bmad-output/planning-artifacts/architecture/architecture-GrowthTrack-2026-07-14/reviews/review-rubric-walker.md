---
review: rubric-walker
target: ../ARCHITECTURE-SPINE.md
date: 2026-07-14
---

# Rubric Walk — ARCHITECTURE-SPINE.md (GrowthTrack Phase 1)

## Verdict

Solid, well-constructed spine — paradigm, dependency direction, stack, and the capability map are all sound and template-conformant — but it leaves real divergence points unfixed in three places (audit-log rule under-coverage, opt-in enforcement, concurrent-edit handling) and is silent on the operational/infra envelope the checklist specifically warns against leaving silent. Recommend one more pass before calling this final.

## Checklist-by-checklist findings

### 1. Fixes the real divergence points for the level below

**Gap — operational/environmental envelope only half-covered [HIGH]**
AD-5 fixes deployment *topology* (Compose services, staging/prod parity, secrets-as-env-vars) but the broader envelope the checklist calls out by name — infra/provider strategy and operations — is silent, not decided/deferred/open-question:
- No hosting/cloud provider or region is named anywhere (not even in Deferred, despite the PDPA residency item in Deferred depending on exactly this decision).
- No restart-policy/health-check mechanism is specified to satisfy SPEC.md's explicit constraint "System must maintain 99.5% uptime with automatic recovery after failures" — AD-2's single in-process scheduler is a named single point of failure with no stated recovery mechanism.
- No monitoring/alerting or backup/DR story for Postgres — "structured JSON logging" (Consistency Conventions) covers emission, not where logs/metrics go or who's alerted.
- PRD §12 explicitly flags "support/on-call model and RTO/RPO" as an open question (#10) — the spine doesn't even carry this forward into its own Deferred/open-questions, so a reader of the spine alone would not know this gap exists.
Two feature teams could each stand up "their" service with a different restart policy, a different hosting target, and no shared monitoring convention, and nothing in the spine would flag the divergence.

**Gap — no single opt-in/opt-out enforcement choke-point [MEDIUM]**
FR-10 is a hard gate ("a Recipient cannot receive Scheduled or Manual notifications until opt-in is recorded," "opt-out... immediately stops future sends"). This is structurally identical to the problem AD-8 solves for auth (one shared gate, no route/path allowed to skip it) — but no AD does the equivalent for consent. `OPT_IN_CONSENT` appears only as an ERD box; no rule says the scheduled-send path and the manual-send path must both check it through the same mechanism before dispatch. This is exactly the kind of "two independently-built send paths assuming different things" divergence AD-2 was written to prevent for dedup — the same risk applies here and isn't covered.

**Gap — concurrent-edit conflict handling unaddressed [MEDIUM]**
EXPERIENCE.md (State Patterns → "Conflict") commits to concrete behavior: "editing a Recipient record that someone else just changed surfaces a conflict dialog showing both versions; it never silently overwrites." PRD §13 also explicitly names "concurrent-edit locking" as an item flagged for downstream architecture. The spine has no versioning/optimistic-concurrency convention (no version column, no ETag/If-Match pattern, nothing in Consistency Conventions) to back this UX commitment. Absent a shared mechanism, Recipients/Teams/RecipientLists CRUD surfaces are free to implement (or not implement) conflict detection independently — a real, product-visible divergence, not a cosmetic one.

**Minor completeness gaps in Deferred:**
- Retention period for Audit Log / Notification History (PRD Open Question #9, FR-12) is not listed in Deferred alongside the structurally similar "exact retry policy magnitude / JWT TTL" line — but retention has real schema/purge-job implications (append-only table growth; whether a purge job lives in `scheduler/`), unlike a pure business-formula question. Worth adding for parity.
- Achievement %/Growth % formula ambiguity (PRD §13 open question #3) sits squarely inside `domain/metrics`, which the Capability Map explicitly assigns to CAP-2/CAP-6, but isn't mentioned in Deferred the way "Brand top/low/focus ranking thresholds" is. Same category of item, inconsistent inclusion.

### 2. Every AD's Rule is enforceable and actually prevents its stated divergence

Seven of eight ADs are tight and enforceable (AD-1, AD-2, AD-3, AD-4, AD-5, AD-6, AD-8 all give a builder a concrete, one-reading rule). One has a real gap:

**AD-7 doesn't fully cover what it binds [HIGH]**
- AD-7 **Binds:** FR-12, CAP-5. FR-12 explicitly requires "Login events are recorded" as part of the Audit Log. But AD-7's **Rule** only fires "every service method that mutates a Recipient, Team, RecipientList, opt-in/out state, or the Daily Report schedule" — a login is not a mutation of any of those, so the literal rule text does not obligate anyone to audit-log logins, even though the AD claims to bind FR-12 in full.
- Separately, "Recipient" in AD-7's rule (and again in the Consistency Conventions row: "All writes to `Recipient`/`Team`/`Notification`/`User`...") is not a table AD-4 ever defines — AD-4's entity list is `User`, `Team`, `RecipientList`, `Notification`, `NotificationDelivery`. There is no `Recipient` table. A builder implementing User-account CRUD (creating/deactivating a Sales Rep or Administrator record) has no clear answer to "does mutating a `User` count as mutating 'a Recipient' for AD-7's purposes?" — the naming convention row's own promise ("Domain vocabulary is PRD-glossary-verbatim... no per-layer renaming of the same concept") is undercut by this ADs using an entity name the data model itself doesn't have.
- Net effect: AD-7's Rule can be read two ways on two separate points (does it cover login? does it cover User?) — exactly what the checklist asks to catch.

### 3. Nothing under Deferred lets two units diverge in a way that matters

Reviewed all nine Deferred items (Redis/Celery, WhatsApp provider migration, secrets manager, PDPA residency, retry/TTL magnitudes, ranking thresholds, Source System identity, bulk import, multi-Team membership) — each is genuinely a value/business-decision/future-event, not a structural fork, and each names why it can wait. No issue here; the problem is what's missing *from* Deferred (see §1 and the two minor items above), not what's wrongly included in it.

### 4. Named tech is verified-current

Spot-checked 8 of the 12 pinned entries against real release data for 2026-07-14:

| Package | Spine version | Verified |
| --- | --- | --- |
| FastAPI | 0.139.0 | Confirmed — released 2026-07-01 |
| PostgreSQL | 18.4 | Confirmed — "PostgreSQL 18.4, 17.10, 16.14, 15.18, and 14.23 Released" |
| React | 19.2.7 | Confirmed — latest as of June 2026 |
| MUI (@mui/material) | 9.2.0 | Confirmed — published ~9 days before 2026-07-14 |
| SQLAlchemy | 2.0.51 | Confirmed — released 2026-06-15 (correctly avoids the 2.1.0b2 beta) |
| Alembic | 1.18.5 | Confirmed — released 2026-06-25 |
| Twilio Python SDK | 9.10.9 | Confirmed — released 2026-05-07 |
| PyJWT | 2.13.0 | Confirmed — released 2026-05-21 |

All eight check out exactly. No stale or fabricated versions found.

**But — "current stable" is not a version [LOW]**
The Stack section's footer claims *all* versions were "verified current against PyPI/npm/vendor release pages on 2026-07-14," yet two rows dodge an actual pin:
- Nginx → "current stable" (actual: 1.30.3, confirmed released 2026-06-17 — pinnable)
- Docker / Docker Compose → "current stable" (actual: Compose 5.3.1 / Engine v29.x — pinnable)

This is inconsistent with the template's "Name + version only" instruction and with the rigor visibly applied to every other row — either pin the real numbers or don't claim uniform verification.

Also minor: the Pydantic row gives only "v2 (bundled with FastAPI 0.139)" rather than an exact pin — Pydantic ships and versions independently of FastAPI (it's a dependency, not a bundled component), so "bundled with" is an imprecise characterization even if the intent (don't separately pin, it rides FastAPI's constraint) is reasonable.

### 5. Every initiative-altitude dimension is decided/deferred/open

Covered: paradigm, dependency direction, scheduling/idempotency mechanism, delivery-status feedback, entity ownership, deployment topology (partial — see §1), source-system ingestion contract, audit co-transactionality (partial — see §2), auth choke-point, naming/data-format/state conventions, stack, source tree, capability map.

Not covered anywhere (decided, deferred, or flagged open): infra/hosting provider, monitoring/alerting, backup/DR, restart/health-check policy for the "automatic recovery" NFR, opt-in/opt-out enforcement mechanism, concurrent-edit/optimistic-locking convention. See §1 for detail — these are the dimension-level gaps the checklist is specifically designed to surface.

### 6. Covers SPEC.md CAP-1 through CAP-8

Confirmed. `binds:` frontmatter lists CAP-1–CAP-8; the Capability → Architecture Map table maps every one of them (plus the cross-cutting Audit Log/FR-12) to a component and a governing AD. No capability is missing from the map.

### 7. Diagrams are valid mermaid, not placeholders

All four diagrams checked and are syntactically valid, non-empty mermaid:
- Design Paradigm dependency-direction graph (`graph LR`) — valid, no empty graph.
- System context (`graph TB`) — valid; uses correct database-cylinder shape `DB[(PostgreSQL)]` and correct edge-label shorthand `Twilio -- status callback --> Nginx`.
- Deployment & environments (`graph TB` with two `subgraph ... [...]` blocks) — valid subgraph-with-title syntax.
- Core-entity ERD (`erDiagram` with `||--o{`, `}o--o{` cardinality tokens) — valid.

Minor clarity nit (not a validity issue): the system-context diagram models `API[api/ - FastAPI]` and `Webhook[api/ webhook receiver]` as two separate boxes even though both live in the same `api/` package per the source tree and AD-3 — not wrong, just a little visually redundant.

### 8. No leftover template-guidance comments

Grepped the document for `<!-- -->` HTML comments and template placeholder braces — none found. The one "TBD" occurrence ("Source System - identity TBD" in the system-context diagram) is intentional prose reflecting PRD Open Question #1, not a stripped-template leftover. Clean on this axis.

## Summary of findings by severity

| # | Severity | Finding |
| --- | --- | --- |
| 1 | High | Operational/infra envelope (hosting/provider, monitoring, backup/DR, auto-recovery mechanism for the 99.5% uptime NFR) is silent — not decided, not deferred, not even carried forward as an open question. |
| 2 | High | AD-7's Rule doesn't literally cover login events (required by FR-12, which it binds) and uses "Recipient" as an entity name that AD-4 never defines as a table — ambiguous, under-inclusive audit rule. |
| 3 | Medium | No AD gives opt-in/opt-out (FR-10) a single enforcement choke-point analogous to AD-8 (auth) or AD-3 (webhook) — scheduled vs. manual send paths can diverge on consent-gating. |
| 4 | Medium | Concurrent-edit conflict handling (committed to in EXPERIENCE.md, flagged in PRD §13) has no backing convention (no versioning/optimistic-locking rule) — each CRUD surface is free to diverge. |
| 5 | Low | Stack table claims uniform "verified current" versioning but Nginx and Docker/Compose use "current stable" instead of a pin, even though pinnable current versions exist. |
| 6 | Low | AD-2's Send Event identity tuple uses an undefined term ("trigger_id") with no corresponding entity/definition elsewhere in the document. |
| 7 | Low | AD-8's absolute "every portal route" rule isn't reconciled with the first-Administrator bootstrap flow EXPERIENCE.md requires. |
| 8 | Low | Retention policy (Audit Log/Notification History) and the Achievement%/Growth% formula question aren't listed in Deferred despite being structurally identical to items that are (retry/TTL magnitudes; ranking thresholds). |
