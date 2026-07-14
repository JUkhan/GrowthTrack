# Phase 2 Roadmap: AI-Based Sales Forecasting

Source: GrowthTrack_SRS_v2.md, in full. Demoted out of Phase 1 scope per user directive (see SPEC.md Non-goals and the memlog decision entry). Preserved here so none of v2's forecasting content is lost — this is the starting material for a future spec update, not an active contract.

## Why (per v2)
Extend the Phase 1 reporting platform with AI-powered sales forecasting for pharmaceutical/FMCG sales organizations.

## Additional Capabilities (candidate, not yet validated as CAPs)
- Monthly sales forecast
- Territory forecast
- Brand demand prediction
- Target achievement prediction
- Low-sales alerts
- Doctor potential scoring

## Additional Data Entity
- **Forecast** (fields not specified in source)
- Also proposed: `Team` as a standalone entity, `NotificationLog` split from `Notification`

## Additional/Changed Non-Functional Requirements (per v2)
- API response < 500 ms (excluding analytics)
- Horizontal scalability

## Additional Tech Stack (per v2)
| Component        | Technology                                    |
| ----------------- | ---------------------------------------------- |
| Cache             | Redis                                          |
| Background Jobs   | Celery                                          |
| AI/ML             | Scikit-learn, LightGBM, XGBoost, Prophet        |
| Auth (proposed)  | OAuth2 (in addition to / instead of JWT — unresolved) |
| API Docs          | OpenAPI / Swagger                               |
| Deployment        | Docker, Nginx, Gunicorn/Uvicorn                 |

Whether Redis/Celery and OAuth2 are Phase 2-only additions or should move earlier into Phase 1 is an open question — see SPEC.md.

## Additional REST Endpoint
```
GET /forecast
```

## AI Pipeline (per v2)
1. Extract sales data
2. Feature engineering
3. Train LightGBM/XGBoost model
4. Generate forecasts
5. Store predictions
6. Display in dashboard
7. Include summary in WhatsApp reports

## System Architecture (per v2)

```text
React + Material UI
        |
     FastAPI
  /      |      \
PostgreSQL Redis Celery
        |
 AI Forecast Engine
        |
 WhatsApp API
```

## Also noted in v2, not yet triaged
- Recommended repository structure (`growthtrack/app/{api,auth,models,schemas,services,forecasting,notifications,whatsapp}`, `alembic/`, `tests/`, `docker/`) — implementation-shape detail for whenever Phase 2 architecture work begins.
