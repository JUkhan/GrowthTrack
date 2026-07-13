
# Software Requirements Specification (SRS)

**Project Name:** GrowthTrack

**Version:** 1.0

**Prepared From:** GrowthTrack Phase 1 Concept Document

---

# 1. Introduction

## 1.1 Purpose

This document defines the software requirements for **GrowthTrack**, a web-based analytics platform that delivers daily sales and marketing performance insights through WhatsApp notifications and provides administrators with a centralized management portal.

The system aims to improve decision-making by providing real-time business performance metrics to sales representatives, managers, and executives.

---

## 1.2 Scope

GrowthTrack will:

* Deliver automated daily WhatsApp reports
* Display key sales performance indicators
* Highlight top-performing and underperforming brands
* Provide targeted doctor lists
* Allow administrators to manage notifications
* Support manual notification triggering
* Broadcast announcements through WhatsApp

Phase 1 focuses on WhatsApp reporting and administrative management.

---

## 1.3 Intended Users

* Sales Representatives
* Area Managers
* Regional Managers
* National Sales Managers
* Marketing Team
* System Administrators
* Company Executives

---

# 2. Overall Description

## 2.1 Product Perspective

GrowthTrack is a web application consisting of:

* Web-based Admin Portal
* Backend REST API
* PostgreSQL Database
* WhatsApp Notification Service

The system integrates with WhatsApp through Twilio API during the Proof of Concept (POC).

---

## 2.2 Product Features

### Daily WhatsApp Notifications

Automatically send performance summaries including:

* Sales Achievement %
* Year-over-Year Growth
* Month-over-Month Growth
* Top Selling Brands
* Brands Requiring Attention
* Targeted Doctors List

---

### Administrative Dashboard

Administrators can:

* View notification history
* Trigger notifications manually
* Send custom WhatsApp messages
* Manage recipients
* Monitor delivery status

---

### Reporting

The system generates daily reports including:

* YTD Sales
* MTD Sales
* Achievement Percentage
* Growth Percentage
* Team Performance

---

# 3. Functional Requirements

## FR-1 User Authentication

The system shall:

* Allow administrator login
* Authenticate using JWT
* Support secure session management

---

## FR-2 Dashboard

The dashboard shall display:

* Today's sales summary
* YTD Sales
* MTD Sales
* Achievement %
* Growth %
* Team Performance
* Notification Status

---

## FR-3 WhatsApp Notification Engine

The system shall:

* Generate daily reports automatically
* Format messages
* Send WhatsApp notifications
* Retry failed messages
* Log delivery status

---

## FR-4 Manual Notification

Administrator shall be able to:

* Select recipients
* Compose message
* Attach report
* Send immediately

---

## FR-5 Recipient Management

Administrator shall manage:

* Individual users
* WhatsApp Groups
* WhatsApp Channels
* Sales Teams

---

## FR-6 Brand Analytics

The system shall generate:

* Top Selling Brands
* Low Performing Brands
* Recommended Focus Brands

---

## FR-7 Doctor Target List

The system shall display:

* Doctor Name
* Territory
* Target Priority
* Recommended Visit List

---

## FR-8 Notification History

Administrator shall view:

* Date
* Time
* Recipient
* Message Type
* Delivery Status

---

# 4. Non-Functional Requirements

## Performance

* Dashboard loads within 3 seconds
* Notification generation under 60 seconds
* Support 500+ concurrent users
* Deliver notifications within 5 minutes of scheduled execution

---

## Security

* JWT Authentication
* HTTPS communication
* Password encryption
* Role-based access control
* Audit logs

---

## Availability

* 99.5% uptime
* Automatic recovery after failures

---

## Scalability

System should support:

* Additional sales teams
* More business units
* Higher notification volume
* Future analytics modules

---

## Reliability

* No duplicate notifications
* Automatic retry on failures
* Complete logging

---

# 5. User Roles

## Administrator

Permissions:

* Login
* Manage users
* Trigger notifications
* Configure settings
* View reports
* Monitor delivery logs

---

## Sales User

Permissions:

* Receive WhatsApp reports

---

## Manager

Permissions:

* Receive reports
* View team performance

---

# 6. System Workflow

```
Sales Database
        │
        ▼
Backend API
        │
        ▼
Generate Daily Metrics
        │
        ▼
Prepare WhatsApp Message
        │
        ▼
Twilio WhatsApp API
        │
        ▼
Recipients
```

---

# 7. Database Entities

## User

* UserID
* Name
* Mobile
* Role
* Status

---

## Notification

* NotificationID
* Message
* Recipient
* Status
* SentTime

---

## SalesData

* Date
* SalesAmount
* Achievement
* Growth
* Team

---

## BrandPerformance

* BrandID
* BrandName
* Sales
* Rank
* Growth

---

## Doctor

* DoctorID
* Name
* Territory
* Priority

---

# 8. External Interfaces

## WhatsApp API

Provider:

* Twilio WhatsApp API (POC)

Functions:

* Send Message
* Delivery Status
* Authentication

---

## REST API

Endpoints (examples)

```
POST /login

GET /dashboard

GET /reports/daily

POST /notifications/send

GET /notifications/history

GET /brands

GET /doctors

GET /teams
```

---

# 9. Technology Stack

| Layer          | Technology                    |
| -------------- | ----------------------------- |
| Frontend       | React + Material UI           |
| Backend        | Python FastAPI                |
| Database       | PostgreSQL                    |
| ORM            | SQLAlchemy + Alembic          |
| Authentication | JWT                           |
| Messaging      | Twilio WhatsApp API           |

---

# 10. Sample WhatsApp Report

```
📊 GrowthTrack Daily Report

YTD Sales : 100 Cr BDT

MTD Sales : 12 Cr BDT

MTD Achievement : 40%

MTD Growth : 10%

Team A : 45%

Team B : 50%

Team C : 40%

Top Brand:
ABC Pharma

Focus Brand:
XYZ Pharma

Top Doctors:
• Dr. Rahman
• Dr. Hasan
• Dr. Ahmed
```

---

# 11. Future Enhancements

* Interactive analytics dashboard with charts
* Image-rich WhatsApp messages
* Power BI integration
* Email notifications
* Push notifications
* Mobile application (Android/iOS)
* AI-based sales forecasting
* Scheduled report customization
* Multi-language support
* Export reports to PDF and Excel

---

## Assumptions and Open Questions

The source document is a high-level concept rather than a complete specification, so several details will need clarification before development:

* **Source of sales data:** ERP, CRM, or another database?
* **Notification schedule:** What time should daily reports be sent, and should users be able to customize it?
* **User management:** Will users be created manually or synchronized from an existing system (e.g., Active Directory or HRIS)?
* **Recipient model:** How are users mapped to WhatsApp groups, channels, or individuals?
* **Brand and doctor data:** What systems provide these datasets, and how frequently are they updated?
* **Authorization model:** Besides administrators, will managers have access to the web portal?
* **KPIs:** Exact formulas for Sales Achievement%, YoY Growth%, and MoM Growth% should be defined.
* **POC vs. production:** Twilio is suitable for a proof of concept; a production deployment may require a WhatsApp Business Platform provider approved for your region.

This SRS provides a solid foundation for software design and estimation while identifying the areas that require further business analysis.
