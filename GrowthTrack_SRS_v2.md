# Software Requirements Specification (SRS)

## Project
**GrowthTrack – AI-Powered Sales & Marketing Analytics Platform**

**Version:** 2.0

## 1. Purpose
GrowthTrack is an enterprise sales analytics platform that delivers automated WhatsApp reports, AI-powered sales forecasting, and a web-based administration portal for pharmaceutical or FMCG sales organizations.

## 2. Scope
Phase 1 includes:
- Daily automated WhatsApp KPI notifications
- Admin portal
- Manual notification trigger
- Sales dashboard
- Brand performance analytics
- Doctor targeting list
- AI-based sales forecasting

## 3. Users
- Sales Representatives
- Area Managers
- Regional Managers
- National Sales Managers
- Marketing Team
- Executives
- System Administrators

## 4. Functional Requirements

### Authentication
- JWT/OAuth2 authentication
- Role-based access control

### Dashboard
- YTD/MTD sales
- Sales Achievement %
- YoY Growth %
- MoM Growth %
- Team performance
- Top & Focus brands
- AI Forecast widgets

### WhatsApp Notifications
- Scheduled daily reports
- Manual notifications
- Groups, channels, individuals
- Delivery logs and retry

### AI Forecasting
- Monthly sales forecast
- Territory forecast
- Brand demand prediction
- Target achievement prediction
- Low-sales alerts
- Doctor potential scoring

## 5. Non-Functional Requirements
- API response < 500 ms (excluding analytics)
- Dashboard load < 3 seconds
- 99.5% uptime
- HTTPS everywhere
- Audit logging
- Horizontal scalability

## 6. System Architecture

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

## 7. Technology Stack

| Component | Technology |
|---|---|
| Frontend | React + Material UI |
| Backend | Python FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy + Alembic |
| Authentication | JWT / OAuth2 |
| Cache | Redis |
| Background Jobs | Celery |
| AI/ML | Scikit-learn, LightGBM, XGBoost, Prophet |
| Messaging | Twilio or Meta WhatsApp Business API |
| API Docs | OpenAPI / Swagger |
| Deployment | Docker, Nginx, Gunicorn/Uvicorn |

## 8. Database Entities
- User
- Team
- SalesData
- BrandPerformance
- Doctor
- Forecast
- Notification
- NotificationLog

## 9. REST APIs
- POST /auth/login
- GET /dashboard
- GET /forecast
- GET /brands
- GET /doctors
- POST /notifications/send
- GET /notifications/history

## 10. AI Pipeline
1. Extract sales data
2. Feature engineering
3. Train LightGBM/XGBoost model
4. Generate forecasts
5. Store predictions
6. Display in dashboard
7. Include summary in WhatsApp reports

## 11. Future Enhancements
- Power BI integration
- Mobile app
- Voice assistant
- LLM-powered sales insights
- Geo analytics
- Inventory forecasting

## 12. Recommended Repository Structure

```text
growthtrack/
 app/
   api/
   auth/
   models/
   schemas/
   services/
   forecasting/
   notifications/
   whatsapp/
   main.py
 alembic/
 tests/
 docker/
```
