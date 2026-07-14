---
title: GrowthTrack Phase 1 PRD — Addendum
created: 2026-07-14
updated: 2026-07-14
---

# Addendum: GrowthTrack Phase 1

Supporting depth that informed `prd.md` but doesn't belong in the PRD's main narrative — market research, options-considered rationale, and technical-how notes for downstream architecture work.

## A1. Market & Competitive Context

*(Source: web research sweep, 2026-07-14)*

**Comparable products.** No product was found that uses WhatsApp as the *primary* channel for pushing sales dashboards/reports to reps and leadership — this is a genuine differentiator for GrowthTrack. The nearby category is India-centric pharma/FMCG sales-force-automation (SFA) tooling — SANeForce, Salestrip, Zoulte, Bizzfield, Grahaak, instaMD, Repzo, BeatRoute — built around geo-verified doctor-visit check-ins and in-app dashboards, with WhatsApp bolted on only for narrow follow-up nudges (e.g., instaMD triggers a WhatsApp message when a doctor requests a sample). Several of these vendors already serve Bangladesh/Nepal/Sri Lanka alongside India (SANeForce, Zoulte), confirming the region is an active market for this product category. Enterprise players (Veeva CRM, Salesforce Life Sciences Cloud) are full HCP-engagement suites — heavier and pricier than a realistic Phase 1 comparator.

**Common feature sets.** Pharma/FMCG SFA tools converge on geo-verified visits, digitized call reports, real-time achievement/target dashboards, route planning, and role-based hierarchy views. WhatsApp broadcast platforms (Wati, AiSensy, SleekFlow) emphasize segmented targeting (contacts/groups/tags), template-approval workflow management, delivery/read audit trails, and role-based admin access. GrowthTrack's scoped feature set (recipient management across individuals/groups/teams, manual trigger, dashboard fields, audit history) matches market-standard expectations on both sides — this validates the PRD's scope rather than suggesting expansion.

## A2. WhatsApp Business Solution Provider — Production Decision (Deferred, Non-Goal for Phase 1)

Phase 1 explicitly stays on Twilio as a POC-only provider (see PRD Non-Goals). This section preserves the comparison data for whoever picks up the production-provider decision later.

- **Pricing model shift**: Meta moved to per-delivered-template-message billing on 2025-07-01. Rates vary by country/category; Marketing-category messages cost far more than Utility/Authentication (~80–90% cheaper). GrowthTrack's Daily Report is business-initiated (outside any free 24h service window), so every send is a billed template — cost scales directly with recipient count × send frequency.
- **Provider comparison**:
  - **Twilio** — flat ~$0.005/msg platform fee on top of Meta's per-message rate. Good DX/docs for POC; pricier at scale.
  - **360dialog** — near pass-through Meta pricing (~$49/mo + minimal markup); suits teams that already own their CRM/portal layer, as GrowthTrack does.
  - **Gupshup** — dominant South/Southeast Asia volume pricing; WhatsApp Partner of the Year 2023–2024.
  - **Bangladesh-local resellers** (Whatsfly, FBIP) — BDT billing, Bangla support; worth evaluating for production given the confirmed Bangladesh deployment locale.
- **Recommendation for whoever revisits this**: keep Twilio for POC/Phase 1; evaluate 360dialog, Gupshup, or a local BDT-billing reseller for production based on actual message volume once real usage data exists.
- **Template approval timing**: usually minutes to 2 hours via automation, but up to 24–48 hours on human review for new/unverified WhatsApp Business Accounts or health-adjacent content — build a launch-schedule buffer around this regardless of provider.
- **Template category**: GrowthTrack's report is internal/operational and likely qualifies as the cheaper Utility category rather than Marketing — but Meta classifies by actual content, so this must be verified at template submission time, not assumed.

## A3. WhatsApp Opt-In & Compliance Notes

Meta's Nov 2024 policy requires opt-in before business messaging (a general opt-in is acceptable — no WhatsApp-specific language required — but the business must be named and an opt-out path provided). Neither source SRS addressed this; the PRD adds an Opt-In Consent capture requirement to Recipient & Directory Management (FR-10, which references this addendum) to preempt a launch blocker at WhatsApp Business Account verification time.

Pharma HCP promotional-compliance codes (the kind that govern marketing content directed *at* doctors) do not directly apply to Phase 1, because GrowthTrack's messages go to internal staff (reps/managers/executives) — the doctor list is a targeting *aid* for reps' own field activity, not a message sent to doctors. **This is product-team reasoning, not a legal or regulatory determination** — unlike the data-residency question (§A4), it has not been reviewed by counsel. It's treated as low-risk enough to proceed without blocking Phase 1, but if a future phase considers messaging HCPs directly, this exemption needs formal re-examination, not just extension of this same reasoning.

## A4. Data Residency — Detail Behind the Pre-Launch Legal Review Flag

Bangladesh's Personal Data Protection Act (2026, partially effective since 2025-11) requires a synced, real-time in-country copy of data classified "restricted"/"confidential" or tied to Critical Information Infrastructure, and restricts cross-border transfer absent an "adequate protection" designation (not yet defined by the Bangladeshi government as of this writing). GrowthTrack's sales figures and doctor/territory visit lists flow through Twilio's and Meta's infrastructure, which is not Bangladesh-hosted. Whether this data classification triggers the Act's localization requirement is exactly the kind of determination that needs a legal opinion, not a product assumption — hence the PRD treats it as an open item for legal review rather than guessing at a hard NFR. If legal review determines localization is required, it will likely reshape the WhatsApp BSP decision (§A2) toward a provider or architecture that can guarantee in-country data handling.

## A5. RBAC Reconciliation Rationale

SPEC.md carried an unresolved tension: CAP-1 named only "Administrator" as the portal-login role, while a constraint required role-based access control across three roles (Administrator, Sales User, Manager). The user resolved this by choosing WhatsApp-only delivery for Sales User and Manager roles — they never authenticate to the portal in Phase 1. The RBAC constraint therefore still holds at the data-model level (the `Role` field on `User` exists and is used to route/format WhatsApp content appropriately per role) and at the portal-route level (every portal route enforces Administrator-only access) — it just has a narrower present-day surface than "all three roles can log in." This is worth revisiting explicitly if a future phase adds portal access for Managers or Sales Users, since the RBAC enforcement logic would need to expand from a single-role gate to true multi-role authorization.

## A6. Recipient Group / Recipient Channel — Technical Feasibility Note

`entities.md`'s five-entity inventory (User, Notification, SalesData, BrandPerformance, Doctor) has no counterpart for "Recipient Group" or "Recipient Channel." Twilio's WhatsApp product sends template messages to individual phone numbers only — there is no Business API mechanism to broadcast into a live WhatsApp Group, and WhatsApp Channels use a separate, more restricted broadcast mechanism that doesn't fit the template-billing model this PRD assumes. Read literally, CAP-5's "WhatsApp groups, WhatsApp channels" language (inherited from the source SRS) would be technically infeasible on Twilio as scoped.

The PRD resolves this by treating Recipient Group and Recipient Channel as **GrowthTrack-internal saved sets of individual Users** — named distribution lists the Administrator manages in FR-9 — rather than live WhatsApp platform objects. Sending to a Group or Channel fans out to each member's individual phone number via Twilio's standard template-message API, the same mechanism used for an individual Recipient. This is the most plausible reading of the source SRS's intent (a convenient targeting abstraction, not a request to build against a WhatsApp Groups broadcast API that doesn't exist for businesses) and resolves the entities.md modeling gap at the same time: Group/Channel don't need their own entity type distinct from a saved collection of User references.

If this reading is wrong — if the source SRS actually intended literal WhatsApp Group/Channel broadcast — that's a scope-level conversation to have before architecture starts, not an implementation detail to discover mid-build.
