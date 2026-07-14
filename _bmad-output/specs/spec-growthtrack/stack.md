# Phase 1 Technology Stack & API Surface

Source: GrowthTrack_SRS_v1.md §9, §8. This is implementation-shape reference for architecture/dev, not part of the WHAT contract.

## Stack

| Layer          | Technology           |
| -------------- | -------------------- |
| Frontend       | React + Material UI  |
| Backend        | Python FastAPI       |
| Database       | PostgreSQL           |
| ORM            | SQLAlchemy + Alembic |
| Authentication | JWT                  |
| Messaging      | Twilio WhatsApp API  |

Phase 2 adds Redis, Celery, and an AI/ML stack — see `roadmap-phase2.md`. Whether any of that infrastructure is actually needed earlier, in Phase 1, is an open question (logged in SPEC.md).

## REST Endpoints (examples, from source concept doc — not exhaustive)

```
POST /login
GET  /dashboard
GET  /reports/daily
POST /notifications/send
GET  /notifications/history
GET  /brands
GET  /doctors
GET  /teams
```

## External Interface: WhatsApp API

Provider: Twilio WhatsApp API (POC only — see Non-goals in SPEC.md for production-provider decision).

Functions: Send Message, Delivery Status, Authentication.
