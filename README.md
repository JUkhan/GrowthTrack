# GrowthTrack

Sales performance visibility and automated WhatsApp reporting. See
`_bmad-output/planning-artifacts/architecture/architecture-GrowthTrack-2026-07-14/ARCHITECTURE-SPINE.md`
for the full architecture spine.

## Source tree

```
api/                    inbound HTTP adapter — FastAPI routers, incl. webhook receiver
domain/                 core services: metrics, ranking, notification orchestration — no external deps
ports/                  abstract interfaces domain depends on
adapters/
  whatsapp_twilio/      Twilio implementation of the WhatsApp port
  source_system/        nightly batch importer implementation
  persistence/          SQLAlchemy repositories implementing domain repository ports
scheduler/               APScheduler jobs — own process entrypoint, separate from api/ (AD-5)
web/                     React + MUI admin portal
alembic/                 DB migrations
tests/
docker/                  Dockerfiles + compose definitions
```

`domain/` imports only from `ports/` (AD-1), enforced by `import-linter` in CI.

## Local development

Backend:

```
uv sync
cp .env.example .env   # fill in real values
uv run uvicorn api.main:app --reload
```

Frontend:

```
cd web
npm install
npm run dev
```

Full stack (API, scheduler, PostgreSQL, Nginx):

```
docker/certs/generate-dev-cert.sh   # local-only self-signed TLS cert
docker compose -f docker/docker-compose.yml --env-file .env up --build
```

### Seed demo data

Populates a fresh environment with Teams, a Sales User/Manager roster,
RecipientLists (with membership), opt-in consents, a demo `MessageTemplate`,
a full year-to-date SalesData time series, a BrandPerformance snapshot, a
Doctor snapshot, and one succeeded ImportRun — everything the Dashboard,
Recipients, Notifications, and Doctor Visit List screens read from. Does
not create an Administrator account (that only comes from the bootstrap
flow); requires migrations to already be applied (`uv run alembic upgrade
head`).

```
uv run python -m scripts.seed_demo_data
```

Safe to re-run — Teams/RecipientLists/the demo template are looked up by
name and roster Users by mobile before creating anything new, and
SalesData/BrandPerformance/Doctors upsert in place. The seeded
`MessageTemplate`'s `twilio_content_sid` is a placeholder — swap in a real
Content SID from the Twilio Console before sending a real WhatsApp message
through it.

**Inside the Docker Compose stack:** the `api`/`scheduler` images bundle
`scripts/`, so once the stack is up (`docker compose ... up --build`) and
the `api` service is healthy (migrations have run), exec into it directly —
no separate `uv`/Python install needed on the host:

```
docker compose -f docker/docker-compose.yml --env-file .env exec api python -m scripts.seed_demo_data
```

## Guardrail

The source tree, Docker Compose deployment topology, and CI configuration are
established once, by Story 1.0 (Project Scaffolding & Deployment Foundation).
No later story re-scaffolds them — later stories build directly on this
foundation (add packages/modules within it, extend `docker-compose.yml`
incrementally, add CI steps as needed), rather than re-establishing project
structure, container topology, or CI configuration from scratch.



Who gets it: Every active User in the system who has a mobile number on file and active WhatsApp opt-in consent. It's not role-based, not per-client/account, and not a curated recipient list — it's derived from the whole user directory at send time.

Where it happens:
- scheduler/main.py — the scheduler fires _run_daily_report_async when the current UTC time crosses the configured send time (ReportSchedule.send_hour_utc/send_minute_utc).
- domain/scheduled_notifications.py (ScheduledReportService.run_daily_report, lines ~107-277) — pulls all users, filters to status == ACTIVE, then hands them to the shared recipient-resolution service.
- domain/notifications.py (RecipientResolutionService.resolve, lines ~104-155) — applies the final eligibility filter.

Final filter (exact logic):
for user_id in deduped_ids:
    user = users_by_id.get(user_id)
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or user.mobile is None
        or user_id not in active_consent_by_user
    ):
        ineligible_count += 1
        continue
    sendable_ids.append(user_id)
So a user must: exist → be ACTIVE → have a mobile number → have an active OptInConsent row. Administrators are excluded in practice (they typically have no mobile), but that's incidental — there's no explicit role filter.

What's NOT involved: RecipientList ("Groups/Channels") and Team-based targeting from Story 4.1 exist only for the manual notification compose flow. The daily report explicitly passes team_ids=[] and recipient_list_ids=[], bypassing them entirely (see comment at domain/scheduled_notifications.py:119-121).

What Story 4.4 actually configures: just the send time, stored as a singleton ReportSchedule row and edited via SettingsPage.tsx / GET/PATCH /settings/report-schedule. The implementation doc for that story explicitly notes: "no per-recipient customization exists in Phase 1."

Content personalization: while recipients aren't filtered by team, the report content each user sees is scoped by Territory — derived by matching the user's Team.name against Doctor.territory (case-insensitive), per DailyReportContentService.resolve_territories.
