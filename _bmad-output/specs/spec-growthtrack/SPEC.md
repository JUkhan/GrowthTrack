---
id: SPEC-growthtrack
companions: [entities.md, stack.md, architecture-diagrams.md, sample-whatsapp-report.md, roadmap-phase2.md]
sources: [../../../GrowthTrack_SRS_v1.md, ../../../GrowthTrack_SRS_v2.md]
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability only — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# GrowthTrack — Phase 1 (WhatsApp Sales Reporting & Admin Portal)

## Why

Sales representatives, managers, and executives at a pharmaceutical/FMCG sales organization lack timely visibility into daily sales performance, brand trends, and which doctors to prioritize for visits — a vision to realize: deliver that visibility automatically, every day, through the channel field staff already use (WhatsApp), while giving administrators a portal to manage, trigger, and audit those notifications. This spec reconciles two conflicting concept drafts (a lean WhatsApp-reporting version and an expanded version that adds AI forecasting) by locking Phase 1 to the reporting-and-management scope and deferring AI forecasting to Phase 2 (`roadmap-phase2.md`), per explicit user direction.

## Capabilities

- **CAP-1**
  - **intent:** Administrator can log in and hold a secure session via JWT-based authentication.
  - **success:** Unauthenticated requests to admin routes are rejected; a valid session expires or invalidates per policy.

- **CAP-2**
  - **intent:** Administrator can view a single dashboard summarizing today's sales, YTD sales, MTD sales, Achievement %, Growth %, team performance, and notification status.
  - **success:** All seven fields render from current data within the 3-second load constraint.

- **CAP-3**
  - **intent:** System automatically generates and sends a formatted daily WhatsApp performance report to configured recipients, retrying failed sends and logging delivery status.
  - **success:** Each configured recipient receives exactly one correctly formatted report (matching `sample-whatsapp-report.md`) within 5 minutes of the scheduled run, or a logged failure with retry attempts recorded.

- **CAP-4**
  - **intent:** Administrator can select recipients, compose a custom message, optionally attach a report, and send a WhatsApp notification immediately.
  - **success:** The message reaches selected recipients without waiting for the scheduled run, and appears in notification history.

- **CAP-5**
  - **intent:** Administrator can manage the recipient directory — individual users, WhatsApp groups, WhatsApp channels, and sales teams — used to target notifications.
  - **success:** Adding, editing, or removing a recipient, group, channel, or team changes who future notifications reach.

- **CAP-6**
  - **intent:** System surfaces top-selling brands, low-performing brands, and recommended focus brands from current sales data.
  - **success:** All three lists compute from a given dataset and are reflected in both the dashboard and the daily WhatsApp report.

- **CAP-7**
  - **intent:** System surfaces a prioritized doctor visit list per territory (name, territory, target priority).
  - **success:** Each report includes a doctor list ranked by target priority for the relevant territory.

- **CAP-8**
  - **intent:** Administrator can view a full history of sent notifications (date, time, recipient, message type, delivery status).
  - **success:** Every notification the system sends, scheduled or manual, appears in history with accurate status the same operational day.

## Constraints

- Dashboard must load within 3 seconds.
- Automated notification generation must complete within 60 seconds.
- System must support 500+ concurrent users.
- Scheduled notifications must be delivered within 5 minutes of scheduled execution time.
- All communication must be over HTTPS.
- Passwords must be stored encrypted, never plaintext.
- Access control must be role-based across Administrator, Sales User, and Manager roles.
- All administrative actions must be audit-logged.
- System must maintain 99.5% uptime with automatic recovery after failures.
- No duplicate notifications may be sent for the same send event; failed sends must auto-retry.

## Non-goals

- AI-based sales forecasting (monthly/territory/brand-demand/target-achievement prediction, doctor potential scoring, low-sales alerts) is out of scope for Phase 1 — deferred to Phase 2. Full scope preserved in `roadmap-phase2.md`.
- Interactive charting dashboard, image-rich WhatsApp messages, Power BI integration, email notifications, push notifications, a native mobile app, scheduled report customization, multi-language support, and PDF/Excel export — all listed as future enhancements by the source concept doc, not Phase 1.
- Production-grade WhatsApp Business Platform migration is out of scope; Phase 1 uses Twilio as a POC-only provider.

## Success signal

A recipient receives an accurate, correctly formatted WhatsApp report within 5 minutes of the scheduled daily run, with zero duplicate sends, and an administrator can independently trigger, retarget, and audit any notification — all without touching source data systems directly.

## Assumptions

- Domain is pharmaceutical or FMCG field sales; doctor targeting plus brand performance implies a medical/pharma detailing use case.
- Deployment locale is likely Bangladesh — the sample report uses "Cr BDT" (Bangladeshi crore taka) currency formatting.
- "Doctor" refers to healthcare professionals visited by sales reps, not patients; no patient health data is implicated by the entities described.

## Open Questions

- What system is the source of truth for sales data — ERP, CRM, or another database?
- What time should the daily report run, and can individual recipients customize their schedule?
- Are users created manually, or synced from an existing system such as Active Directory or an HRIS?
- How exactly are users mapped to WhatsApp groups, channels, or individuals for targeting?
- What system(s) supply brand and doctor data, and how often are they refreshed?
- Do managers get direct web-portal access, or only WhatsApp-delivered reports? (v1 grants managers "view team performance" but FR-1 names only Administrator as a portal login role.)
- What are the exact formulas for Sales Achievement %, YoY Growth %, and MoM Growth %?
- Which WhatsApp provider is intended for production — stay on Twilio, or migrate to Meta's WhatsApp Business Platform? (v1 flags Twilio as POC-only; v2 lists both without deciding.)
- Is OAuth2 required for Phase 1 authentication, or is JWT alone sufficient until Phase 2? (v2 adds OAuth2 without stated reason.)
- Is a Redis/Celery background-job layer needed in Phase 1 (e.g., retry queues, scheduling), or is it introduced specifically for Phase 2 forecasting workloads?
- Are pharmaceutical marketing/promotional-compliance rules a concern for how doctors are targeted or prioritized? Neither source document addresses this.
