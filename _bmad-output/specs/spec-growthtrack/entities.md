# Phase 1 Data Entities

Source: GrowthTrack_SRS_v1.md §7. Fields as named in the source; types/constraints are not yet specified and belong to architecture, not this companion.

## User
- UserID
- Name
- Mobile
- Role
- Status

## Notification
- NotificationID
- Message
- Recipient
- Status
- SentTime

## SalesData
- Date
- SalesAmount
- Achievement
- Growth
- Team

## BrandPerformance
- BrandID
- BrandName
- Sales
- Rank
- Growth

## Doctor
- DoctorID
- Name
- Territory
- Priority

## Notes
- v2 additionally proposes `Team`, `Forecast`, and `NotificationLog` entities. `Forecast` belongs to Phase 2 (see `roadmap-phase2.md`). Whether `Team` needs to be a standalone entity (rather than a field on `SalesData`/`User`) and whether `Notification` needs to split into a template/history pair (`Notification` + `NotificationLog`) are open modeling questions for architecture, not resolved by either source document.
