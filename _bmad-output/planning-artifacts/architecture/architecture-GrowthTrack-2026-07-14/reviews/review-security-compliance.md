---
title: GrowthTrack Phase 1 Architecture Spine — Security & Compliance Review
reviewed:
  - ARCHITECTURE-SPINE.md (architecture-GrowthTrack-2026-07-14)
against:
  - prd.md §8 Cross-Cutting NFRs
  - prd.md §9 Constraints and Guardrails
  - prd.md §10 Data Governance
created: 2026-07-14
reviewer-role: security/compliance
---

# Security & Compliance Review — GrowthTrack Phase 1 Architecture Spine

## Verdict

The spine's structural decisions (hexagonal isolation of the WhatsApp adapter, co-transactional audit writes, single auth choke-point, DB-enforced idempotency) are sound and PDPA/security-aware in spirit, but several invariants are underspecified exactly where the PRD states a hard constraint or explicit requirement — the public webhook has no replay/rate-limit/malformed-payload story, JWT session handling has no revocation or key-rotation story despite FR-1 requiring "invalidation," the PRD's "all communication over HTTPS" hard constraint has no owning rule anywhere in the spine, and AD-7's audit invariant as literally written would not fire for the login events FR-12 explicitly requires — these are gaps to close before or during Phase 1 build, not blocking flaws in the spine's overall shape.

---

## 1. Public webhook — `POST /webhooks/twilio/status` (AD-3)

**Finding 1.1 — No replay-attack protection. [HIGH]**
AD-3 requires Twilio signature verification, which authenticates *who sent* the request but not *when*. Twilio's `X-Twilio-Signature` scheme has no timestamp/nonce component enforced by the receiver by default, so a captured, validly-signed status callback can be replayed indefinitely and will still pass signature verification. Because `NotificationDelivery` status is presumably a forward progression (queued → sent → delivered/read/failed), a replayed *older* status could revert a delivery record backward after a newer status has already landed — directly undermining SM-1 (delivery success rate) and SM-3 (duplicate-send rate, by proxy, since history/status integrity feeds both). AD-2 already established the pattern of DB-enforced idempotency for the *send* path; AD-3 does not extend an equivalent guarantee to the *status-update* path. Recommend: the webhook handler must treat status updates as idempotent/monotonic — ignore or no-op writes that would move a delivery backward in its status lifecycle, keyed on `(message_sid, status)` already seen.

**Finding 1.2 — No rate-limiting or DoS posture for a public, unauthenticated-by-JWT endpoint. [MEDIUM]**
This is the one route in the system intentionally reachable without AD-8's auth choke-point (necessarily so — Twilio can't hold a GrowthTrack session). Nothing in AD-3 or AD-5 states any throttling, request-size limit, or Nginx-layer protection against flooding (accidental Twilio retries storming the endpoint, or a malicious actor hammering it to consume DB connections/idempotency-table writes). Recommend a one-line rule: Nginx enforces a request-rate cap and body-size limit on this path ahead of signature verification.

**Finding 1.3 — No stated behavior for malformed or spoofed payloads. [MEDIUM]**
AD-3 doesn't say what happens when: (a) the signature check fails — presumably reject, but "reject with what response, logged how" is unstated; (b) the payload parses but carries a `MessageSid` that doesn't match any known `NotificationDelivery` row (a foreign/fabricated SID). Silent 200-OK-and-drop vs. logged rejection vs. 500 (which could leak stack traces to an internet-facing endpoint) are materially different security postures and none is chosen. Recommend explicitly stating: signature failure → 4xx, no body detail, structured log entry; unknown SID → logged and dropped, never used to create a new `NotificationDelivery` row.

**Finding 1.4 — Worth stating explicitly, not left implicit: this route is deliberately exempt from AD-8.** Not a defect, but AD-8 says "every portal route" depends on the shared auth dependency; the webhook is not a portal route, and that exemption plus its substitute guard (signature verification) should be said once, explicitly, so a future implementer doesn't either (a) try to bolt the JWT dependency onto it, or (b) treat the absence of AD-8 coverage as an oversight and leave it fully unguarded during a refactor. [LOW]

---

## 2. JWT / session handling (AD-8)

**Finding 2.1 — No logout/revocation mechanism, despite FR-1 requiring one. [HIGH]**
PRD FR-1's testable consequence: "A valid session expires **or can be invalidated per policy**." A pure stateless JWT (what AD-8 describes — "validates the JWT and the Administrator role") cannot be invalidated before its expiry without some server-side revocation state (a blacklist/deny-list table, a session-id indirection, or short-lived access tokens paired with a revocable refresh token). The spine's only related note is in Deferred ("exact... JWT session TTL... left configurable"), which addresses the *TTL magnitude* open question (PRD OQ-11) but not the *invalidation mechanism* FR-1 already commits to as a requirement, not an open question. This is a gap between what FR-1 promises and what AD-8's mechanism can deliver as written.

**Finding 2.2 — No refresh-token strategy stated. [MEDIUM]**
Related to 2.1: if sessions are access-token-only, a short TTL forces frequent re-login (poor UX, no urgency), and a long TTL raises the exposure window of a stolen token with no way to revoke it (per 2.1). No refresh-token/rotation design is mentioned either way, so the trade-off doesn't appear to have been made deliberately.

**Finding 2.3 — No signing-key-rotation story. [MEDIUM]**
AD-5 lists "JWT signing key" among the secrets injected as env vars, but neither AD-5 nor AD-8 says what happens on rotation (planned, or in response to compromise): whether it invalidates every existing session immediately (likely acceptable at Phase 1's small Administrator population, but currently a *side effect*, not a *decision*), or whether a key-id (`kid`)/grace-period scheme is intended. Worth one explicit line, since AD-5 already flags secrets rotation generally as deferred (see §3 below) and this is the one rotation event with an immediate, visible user-facing consequence (forced logout of every Administrator).

**Finding 2.4 — Token algorithm and client-side storage are unstated. [LOW]**
PyJWT supports both symmetric (HS256) and asymmetric (RS256) signing; AD-8 doesn't say which, and — more security-relevant for a React SPA — nothing states where the frontend holds the token (httpOnly Secure cookie vs. `localStorage`/JS-accessible storage). The latter is the more consequential of the two: `localStorage` storage is vulnerable to exfiltration via any XSS bug, which would otherwise be mitigated by an httpOnly cookie. This interacts with the PRD's HTTPS/session-security expectations (§8) and should be pinned down before `api/auth` is built, not discovered ad hoc by whoever implements the frontend auth client.

**Note (not a spine gap):** Login lockout / brute-force throttling is explicitly and knowingly deferred by the PRD itself (§13 closing paragraph, alongside password reset and first-Administrator bootstrap) to downstream UX/story work — this review doesn't re-flag it as a spine omission, but flags that AD-7's requirement to log login events (see §5 below) is exactly the mechanism a future lockout feature would need to key off, so that data should exist even before lockout logic itself is built.

---

## 3. Secrets management (AD-5)

**Finding 3.1 — The PRD's "all communication over HTTPS" hard constraint has no owning rule anywhere in the spine. [HIGH]**
PRD §8 states plainly: "All communication over HTTPS." AD-5 is the invariant that names Nginx as the reverse proxy in front of the API and the webhook endpoint — the natural place to pin this down — but it says nothing about TLS termination, certificate provisioning/renewal (e.g., ACME/Let's Encrypt), HTTP→HTTPS redirect/rejection of plaintext requests, or HSTS. This isn't a stated contradiction of the PRD constraint, but it is a hard NFR left without any invariant enforcing it, which is close enough to a live risk to call out directly: absent an explicit rule, "Nginx sits in front of the API" could be satisfied by a plain HTTP reverse proxy and nobody would have violated a written rule to get there. Recommend adding to AD-5: Nginx terminates TLS for all external traffic (portal and webhook), HTTP requests are redirected or rejected, and cert renewal is part of the deployment story.

**Finding 3.2 — Env-var-only secrets have no rotation process, even at the "no dedicated secrets manager" scale Phase 1 has chosen. [MEDIUM]**
Deferred correctly punts on a *dedicated secrets manager* ("environment variables suffice at Phase-1 scale... revisit at the next real security review") — that scoping call is reasonable for a Phase 1 POC. But rotation *process* is a separate concern from rotation *tooling*: nothing states how a compromised Twilio auth token, DB password, or JWT signing key actually gets rotated in the two-environment Compose topology (a redeploy-with-new-env-var runbook, at minimum) — today that's undefined even manually. Given AD-5 explicitly names these three secret classes, a one-line operational note (documented rotation = update env var + redeploy, no code change required) would close this cheaply.

**Finding 3.3 — No least-privilege DB credential separation. [MEDIUM]**
AD-5 says DB credentials are injected as env vars but doesn't distinguish a migration-capable (DDL) credential from the runtime application credential (DML-only) used by the API/scheduler containers. Alembic migrations need schema-alter rights; the day-to-day API and scheduler processes do not. Running both under one shared Postgres role is a common anti-pattern that widens the blast radius of any credential leak (including via a bug in the very webhook or API surface this review is examining) into full schema control — worth a rule even at Phase 1 scale, since it costs nothing structurally (two Postgres roles) and closes a real gap.

**Finding 3.4 — Secret-scanning / accidental-commit safeguard not mentioned. [LOW]**
"Secrets... are never committed to the repository" is stated as a rule, but no enforcement mechanism (pre-commit hook, CI secret-scan, `.gitignore` coverage for `.env` files) backs it. Low severity since it's a process safeguard rather than an architectural one, but cheap to add as a build-tooling note.

---

## 4. Conflict check against PRD hard constraints

- **"Passwords stored encrypted, never plaintext"** — **No conflict.** The spine's `pwdlib` (bcrypt) choice is a one-way hash, which is the *correct* and stronger implementation of this requirement than reversible encryption would be; PRD's "encrypted" phrasing is the imprecise term here, not the spine's implementation. No action needed.
- **"All communication over HTTPS"** — **Not contradicted, but not affirmatively guaranteed either** — see Finding 3.1. This is the one PRD hard constraint the spine comes closest to leaving exposed, because the invariant that should carry it (AD-5) is silent on TLS specifics.

---

## 5. Audit Log (AD-7) vs. FR-12

**Finding 5.1 — AD-7's rule, as literally written, would not capture login events — which FR-12 explicitly requires. [HIGH]**
FR-12's testable consequences state plainly: "Login events are recorded." AD-7's rule scopes co-transactional audit writes to service methods that "mutate a Recipient, Team, RecipientList, opt-in/out state, or the Daily Report schedule." A login attempt (successful or failed) mutates none of those — it's an authentication event, not a directory/notification-schedule mutation — so an implementer following AD-7 literally would have no obligation to audit-log logins at all, silently failing FR-12 and SM-5 (100% audit completeness) on day one. This needs its own explicit line in AD-7 (or a sibling rule): every login attempt, success or failure, writes an `AuditLogEntry` in the same transaction as the auth outcome is determined. Given SM-C1's counter-metric concern about silent gaps, this is worth closing precisely rather than assuming it falls out of the existing rule.

**Finding 5.2 — "What changed" (diff content) is not pinned down anywhere. [MEDIUM]**
FR-12 requires audit entries to record actor, timestamp, and "what changed" — i.e., a diff, not just the fact that an edit occurred. AD-7 and the spine's ERD fix that an `AuditLogEntry` relationship exists ("acted by") but never fix its field content (before/after values, or a structured change payload). `entities.md` explicitly defers `AuditLogEntry`'s fields to architecture, and this spine doesn't pick that decision up. Left this open, an implementation could satisfy "an audit row exists per mutation" while failing FR-12's actual "what changed" bar (e.g., logging only "Recipient X updated" with no field-level diff). Recommend AD-7 name the minimum entry shape: actor, timestamp, entity/action, and before/after values (or equivalent structured diff).

**Finding 5.3 — Administrator-account mutations are covered only by an indirect reading. [LOW]**
Per the PRD glossary, "Recipient" includes "an individual User," and Administrator accounts are `User` rows with `Role=Administrator` — so AD-7's "mutates a Recipient" wording *does* extend to Administrator-account CRUD (creating/deactivating another Administrator) under a careful reading, satisfying FR-12's "all administrative actions" intent. But the wording invites the opposite misreading (an implementer treating "Recipient" as meaning only WhatsApp-recipient-facing Users, and Administrator-account management as a separate, unaudited concern). Recommend AD-7 either use the entity's actual name (`User`) or add "(including Administrator accounts)" to remove the ambiguity.

---

## 6. PDPA flag — does the spine quietly make later compliance harder?

The PRD explicitly and correctly scopes Bangladesh PDPA residency as a flagged legal-review item that "does not block PRD, architecture, or build work" (§10) — the spine's AD-5 correctly declines to architect around it now. The review below is about assumptions that would be *expensive to unwind* later if legal review does require action, not about re-litigating the deferral itself.

**Finding 6.1 — Hosting region is undetermined-by-silence rather than undetermined-by-decision. [MEDIUM]**
AD-5 is the deployment-topology invariant and is the natural place to carry this flag forward operationally, but it never states that the actual cloud/hosting region for staging and production Postgres/Compose infrastructure is an open item pending the same legal review named in Deferred. As written, whoever stands up the actual staging/production infrastructure could pick a region purely on convenience/cost grounds with no ceremony — at which point "residency wasn't architected around" quietly becomes "residency was accidentally decided" by an unrelated deploy choice, which is a materially worse position for the pending legal review to inherit. Recommend one line in AD-5: hosting region for Postgres/Compose infra is not yet fixed and must not be finalized without the PRD §10 legal-review sign-off.

**Finding 6.2 — Append-only Audit Log + undefined retention is a combination that's cheap now, expensive later. [MEDIUM]**
AD-7 fixes the Audit Log as append-only (correct for tamper-evidence and FR-12's integrity intent), while PRD §10/§13 (OQ-9) leave retention entirely undefined. If the PDPA legal review (or simply a retention policy landing later) requires either a fixed retention window or a right-to-erasure/anonymization path, retrofitting deletion or anonymization into an append-only table that is by then a live compliance record — used as evidence that "every action is accounted for" — is a much larger lift than if the table had been designed with lifecycle management (e.g., date-partitioning, or a documented archive-then-purge path) from the start. This is exactly the kind of assumption the review was asked to look for: nothing forces a redesign today, but nothing in the current shape makes tomorrow's retention/erasure requirement cheap either. Recommend a Deferred-list note flagging this explicitly, so whoever eventually resolves OQ-9 isn't the first person to discover the table has no purge-friendly structure.

**Finding 6.3 — No reserved path for field-level protection (encryption-at-rest/masking) of business-confidential columns. [LOW]**
`SalesData`, `BrandPerformance`, `Doctor`, and `User.Mobile` are the PRD §10-classified "business-confidential" fields; beyond password hashing, nothing in the spine reserves a mechanism for encrypting or masking these at rest. The mitigating factor: AD-1's hexagonal design already puts all persistence behind repository ports, so such protection *could* be added later at the `adapters/persistence` layer without touching `domain/` — this is a genuine structural strength worth naming, not just a gap. But since nothing currently plans for it, it remains a "still requires real work later" item rather than a "already accounted for" one.

**Finding 6.4 (positive, for balance) — The WhatsApp-provider isolation is a real PDPA mitigant, not just a portability convenience.** PRD §10 notes that a PDPA localization requirement "will likely reshape the production WhatsApp provider decision." AD-1/AD-6's hexagonal isolation of `adapters/whatsapp_twilio` behind `ports/` means that if legal review forces a Bangladesh-local BSP swap, it is already scoped as a contained adapter change per the spine's own stated intent (Deferred: "Production WhatsApp provider migration... isolated behind ports/... a future adapter swap, not an architecture change"). This is the one place where the spine's general design choice directly de-risks the flagged PDPA item, and it's worth the review saying so explicitly rather than reading as uniformly critical.

---

## Summary Table

| # | Finding | Severity |
| --- | --- | --- |
| 1.1 | Webhook: no replay-attack protection (stale/duplicate status can revert delivery state) | High |
| 2.1 | JWT: no logout/revocation mechanism despite FR-1 requiring "invalidated per policy" | High |
| 3.1 | No owning rule for PRD's "all communication over HTTPS" hard constraint (TLS/HSTS/redirect unstated at Nginx) | High |
| 5.1 | AD-7 as written would not capture login events, which FR-12 explicitly requires | High |
| 1.2 | Webhook: no rate-limiting/DoS posture stated | Medium |
| 1.3 | Webhook: no defined behavior for malformed/spoofed/unknown-SID payloads | Medium |
| 2.2 | No refresh-token strategy stated | Medium |
| 2.3 | No JWT signing-key-rotation story | Medium |
| 3.2 | No secret-rotation process (even manual) for Twilio/DB/JWT secrets | Medium |
| 3.3 | No least-privilege DB credential separation (migration vs. runtime app) | Medium |
| 5.2 | Audit entry content ("what changed" / diff) not pinned down | Medium |
| 6.1 | Hosting region undetermined-by-silence, not flagged as pending legal sign-off in AD-5 | Medium |
| 6.2 | Append-only Audit Log + undefined retention — expensive to retrofit lifecycle management later | Medium |
| 1.4 | Webhook's exemption from AD-8 should be stated explicitly, not left implicit | Low |
| 2.4 | JWT algorithm and client-side token storage (XSS exposure) unstated | Low |
| 3.4 | No secret-scanning/pre-commit safeguard backing "never committed" rule | Low |
| 5.3 | Administrator-account mutations covered only by indirect reading of "Recipient" | Low |
| 6.3 | No reserved mechanism for field-level encryption/masking of confidential columns (mitigated by AD-1's port isolation) | Low |
| 6.4 | (Positive) WhatsApp-adapter isolation is a genuine PDPA mitigant — worth stating explicitly as such | — |
