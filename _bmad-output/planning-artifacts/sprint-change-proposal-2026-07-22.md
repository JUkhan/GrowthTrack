---
title: Sprint Change Proposal — Message Template Management
created: 2026-07-22
status: approved
---

# Sprint Change Proposal: Message Template Management

## 1. Issue Summary

A Manual Notification send to a real recipient failed with Twilio error `20422: Unable to create record: Invalid Parameter`. Root cause: the notification used the "Target Revision Notice" `MessageTemplate`, whose `twilio_content_sid` is the placeholder value `HXdemoplaceholder0000000000000` seeded by `scripts/seed_demo_data.py:148` — not a real, Twilio/Meta-approved Content SID. That seed script's own comment already flagged this: *"this placeholder Content SID must be swapped for a real one from the Twilio Console before any real send."*

Investigating what "swapping it" actually requires surfaced the real gap: there is no Administrator-facing way to do so. `MessageTemplateRepository` (`ports/notifications.py`) already exposes `add()`/`get_by_id()`/`get_by_name()`/`list_active()`, but no API route or frontend page calls them outside the seed script. The only paths today are a direct database edit or re-running the seed script with a different placeholder — neither is viable for an Administrator in production.

## 2. Impact Analysis

**Epic Impact:** Epic 4 (Automated & Manual WhatsApp Notifications) is otherwise unaffected in its existing stories (4.1 done, 4.2 ready-for-dev, 4.3/4.4 backlog) — this is a pure addition, not a rework. No epic becomes obsolete or blocked.

**Story Impact:** No existing story's acceptance criteria change. A new story is added: **4.5 — Manage Message Templates**.

**Artifact Conflicts:**
- **PRD:** No FR previously covered this — FR-8 only covers *selecting* a pre-approved template, never *entering* one. Added **FR-13** (§4.9) to close the gap, explicitly scoped to exclude the actual Twilio/Meta approval workflow (which correctly remains out of scope per the architecture spine's existing Deferred item).
- **Epics:** Added Story 4.5 under Epic 4, with FR-13 added to the Requirements Inventory and FR Coverage Map.
- **Architecture:** No conflict. `MessageTemplateRepository`'s `add()`/`list_active()`/`get_by_id()` already anticipated this need (see `ports/notifications.py`'s own docstring) — only the API route, domain service method, and frontend page are net-new, following the exact CRUD pattern Stories 3.1/3.2 already established (`RecipientDirectory`-style routes, audit-logged writes, `data-table-row` UI pattern).
- **UX:** No new pattern needed — reuses UX-DR5 (shared data-table), UX-DR8 (button-primary/danger), UX-DR11 (Information Architecture — adds one surface under Settings or a new "Templates" IA entry, implementer's choice at story-dev time).

**Technical Impact:** No migration required — `MessageTemplate` already has every field this story needs (`id`, `name`, `twilio_content_sid`, `variable_slots`, `body_preview_template`, `created_at`); confirmed with the user that no status/active field is being added in this iteration (Create + List + Edit only, no delete/deactivate).

## 3. Recommended Approach

**Selected:** Option 1 — Direct Adjustment (add one story to the existing epic; no rollback, no MVP scope reduction).

**Rationale:** The gap is narrow, additive, and the persistence layer already anticipated it. Effort: **Low** (mirrors Stories 3.1/3.2's already-proven CRUD pattern almost exactly, and this entity is simpler — no soft-delete, no version/conflict handling). Risk: **Low** (no schema migration, no change to any existing route or domain service, purely new surface area).

## 4. Detailed Change Proposals

### PRD (`prd.md`)
- Added §4.9 "Message Template Management" and **FR-13** with testable consequences (create/view/edit, audit-logged, no delete/deactivate, no approval-workflow automation).
- Added "Message Template Management (§4.9)" to §6.1 MVP In Scope.
- Updated the document-purpose line's FR range from "FR-1 through FR-12" to "FR-1 through FR-13" with a dated note.

### Epics (`epics.md`)
- Added FR-13 to the Requirements Inventory and FR Coverage Map (`FR-13: Epic 4`).
- Updated Epic 4's description and "FRs covered" line to include FR-13.
- Added **Story 4.5: Manage Message Templates** with 5 acceptance criteria (create+list+edit, audit logging, explicit no-delete decision, explicit no-approval-automation boundary).

### Sprint Status (`sprint-status.yaml`)
- Added `4-5-manage-message-templates: backlog`, sequenced immediately after `4-1` (done) and before `4-2` (ready-for-dev) — reflecting the user's priority to build this before continuing the rest of Epic 4's backlog, even though it's numbered 4.5 in the epics document.

## 5. Implementation Handoff

**Scope classification:** Minor — direct implementation by the Developer agent, no PO/PM/Architect involvement needed.

**Next steps:**
1. `bmad-create-story` for Story 4.5 (produces the full story-context file `4-5-manage-message-templates.md`)
2. `bmad-dev-story` to implement: domain service (`MessageTemplateService` or extend `domain/notifications.py`), API routes under `api/notifications/routes.py` (or a new `api/templates/routes.py`), frontend page mirroring `RecipientsPage.tsx`'s list/create/edit pattern
3. Code review per repo convention

**Success criteria:** An Administrator can create a `MessageTemplate` with a real Twilio Content SID through the portal UI, see it in a list, and edit it — with zero direct-database access required, closing the gap that caused the original `20422` failure.
