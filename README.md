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

## Guardrail

The source tree, Docker Compose deployment topology, and CI configuration are
established once, by Story 1.0 (Project Scaffolding & Deployment Foundation).
No later story re-scaffolds them — later stories build directly on this
foundation (add packages/modules within it, extend `docker-compose.yml`
incrementally, add CI steps as needed), rather than re-establishing project
structure, container topology, or CI configuration from scratch.
