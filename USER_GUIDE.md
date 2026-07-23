# GrowthTrack User Guide

GrowthTrack gives a pharmaceutical/FMCG sales organization daily visibility
into sales performance, brand trends, and doctor-visit priorities — and
delivers that visibility automatically over WhatsApp — while giving an
Administrator a web portal to manage recipients, trigger notifications, and
audit everything that happens.

This guide covers how to use the application day to day. For local setup and
deployment, see `README.md`. For the underlying business/technical contract,
see `_bmad-output/specs/spec-growthtrack/SPEC.md`.

## 1. Who uses GrowthTrack

- **Administrator** — the only role with web portal access in Phase 1. Logs
  in, manages the recipient directory, sends notifications, configures the
  schedule, and reviews history/audit logs.
- **Sales User / Manager** — do not log into the portal. They receive the
  Daily Report and any manual notifications on WhatsApp, and appear as
  entries in the Administrator's recipient directory.

## 2. Logging in

Open the portal in a browser (`https://<your-deployment-host>/`).

- **First run (no Administrator exists yet):** the Login screen automatically
  shows a **"Create the first Administrator account"** form instead of a
  login form. Enter a username and password to create the first
  Administrator and you're logged straight in. This one-time flow disappears
  once any Administrator account exists.
- **Normal login:** enter your username and password and click **Log in**.
- **Forgot password:** click **Forgot password?** on the login screen, follow
  the link, and set a new password. The reset link is single-use and expires
  after a set time (1 hour by default).
- **Lockout:** after 5 failed attempts (default) within the lockout window,
  the account is temporarily locked and the login button is disabled with a
  live countdown until you can try again.
- **Logging out:** click **Log out** on the Dashboard. This immediately
  invalidates your session token — it can't be reused even before its
  natural expiry.
- If your account is deactivated while you're logged in, your very next
  action returns you to Login with a plain-language explanation, not a
  silent failure.

## 3. Dashboard

The Dashboard (`/dashboard`) is the home screen after login and loads within
3 seconds. It shows:

| Field | What it means |
|---|---|
| Today's Sales | Sales recorded for the current day |
| YTD Sales | Year-to-date sales |
| MTD Sales | Month-to-date sales |
| Achievement % | Progress against target |
| Growth % | Growth trend, with an up/down indicator |
| Team Performance | Achievement % per Sales Team |
| Notification Status | Outcome of the most recent notification sent system-wide (Queued/Sending/Delivered/Retrying/Failed, or "No sends yet") |

All seven fields load together — you'll never see a partial dashboard; while
data loads you see skeleton placeholders for all of them at once.

A **"Data as of HH:MM" badge** (Asia/Dhaka time) shows when the underlying
sales data was last refreshed by the nightly import. If the import is
running late, the badge turns into a warning instead of silently showing
stale numbers as current.

Below the seven core fields, the **Brand Performance** section shows:

- **Top Brands** — best performers
- **Low-Performing Brands** — brands lagging behind
- **Focus Brand(s)** — the brand(s) recommended for a sales push

These three lists are computed once and shared by both the Dashboard and the
Daily WhatsApp Report, so the two never disagree.

On narrow/mobile screens, the stat tiles reflow to a single column without
hiding any field.

Use the **ThemeToggle** in the top bar to switch between light and dark mode;
your choice is saved to your account and follows you across devices.

## 4. Recipients (the directory)

`/recipients` is where you manage everyone and everything a notification can
reach. It has four tabs:

### Users
Individual people (Sales Users or Managers). Fields: Name, Mobile, Role,
Team.

- **Add User** — requires at least one active Sales Team to exist first.
- **Edit** — click Edit on a row (Administrators can't edit themselves here).
  Phone number uniqueness is validated as soon as you leave the field.
- **Remove** — soft-deletes the User (never a hard delete, so history stays
  intact); you'll be asked to confirm, and the confirmation explains the
  real consequence ("Future notifications will no longer reach them").
- **Status** and **Consent** are both shown as color+icon+label badges, so
  you can see at a glance who's Active/Inactive and Opted In/Not Opted In.
- **Opt-in consent** must be recorded before a User can receive WhatsApp
  messages — this is captured directly on the User's edit form. If a User's
  phone number changes, consent is automatically revoked and delivery is
  blocked until fresh consent is recorded for the new number.

### Sales Teams
Named groupings of Users, used both for reporting (Team Performance on the
Dashboard) and as a notification target. Add, edit, or remove the same way as
Users; removal is a soft delete.

### Recipient Groups / Recipient Channels
Named sets of existing Users you can target with one selection instead of
picking individuals every time. Groups and Channels work identically — they
share the same underlying mechanism — and differ only in the label used for
display. Manage membership from each tab's panel.

### Concurrent-edit protection
If two Administrators edit the same User/Team/Recipient List at once, the
second save is rejected as a conflict and a dialog shows both versions side
by side — nothing is silently overwritten.

## 5. Notifications

### Compose (manual send) — `/notifications/compose`

Use this to send an urgent WhatsApp message right now, outside the daily
schedule:

1. **Pick recipients** with the Recipient picker — mix individual Users,
   Sales Teams, and Recipient Groups/Channels freely. A live counter shows
   the de-duplicated total, e.g. "14 selected → 11 unique recipients (3
   overlaps merged)" — someone reachable two ways only gets one message.
2. **Pick a Message Template** from the dropdown, then fill in its variable
   slots (no free-form message body is allowed — every send must use a
   pre-approved WhatsApp template). The right-hand panel shows a **live
   preview** of exactly what recipients will see as you type.
3. Click **Send to N recipients**. The button disables and shows "Sending to
   N recipients…" while in flight — double-submitting isn't possible.
4. If zero recipients are selected, or a variable is left blank, Send stays
   disabled with an inline reason instead of failing silently.

Every manual send appears in Notification History tagged **"Manual"**, and
updates the Dashboard's Notification Status tile once it's the most recent
send.

### Message Templates — `/notifications/templates`

Templates back the composer above. A template must already be approved in
the Twilio/Meta console (GrowthTrack does not submit templates for approval
itself) before you enter it here.

- **Add Template** — enter its Name, Twilio Content SID, variable slot names,
  and preview text.
- **Edit** — update Content SID, variable slots, or preview text; changes
  apply to future sends.
- There is no delete/deactivate for templates in this version — correct a
  template by editing it.

### Automated Daily Report

Once a day, at the time configured in Settings, GrowthTrack automatically
generates and sends a formatted report to every eligible recipient — no
Administrator action needed. Each report includes YTD/MTD sales, Achievement
%, Growth %, Team Performance, top/focus brands, and a prioritized doctor
visit list for the recipient's territory (see `sample-whatsapp-report.md` for
the exact layout). Generation completes within 60 seconds and delivery
within 5 minutes of the scheduled time; recipients reachable through more
than one path (e.g. a User plus their Team) still get exactly one message.

### Delivery status and retries

Every send tracks through `Queued → Sending → Delivered`, or
`Retrying (attempt n of N)`, or `Failed — retries exhausted`, shown
everywhere as a color + icon + text status badge — never color alone. Failed
sends automatically retry up to 3 additional times with increasing delays (1
min, 5 min, 15 min by default) before being marked Failed; a failed
recipient isn't retried again until the next scheduled run or a fresh manual
send. No recipient ever receives a duplicate message for the same send.

## 6. Settings — `/settings`

Configure the **Daily Report Send Time** (Asia/Dhaka / GMT+6). This is a
single global schedule — there's no per-recipient customization in this
version. Change the time and click **Save**; it takes effect on the next
scheduler run, and the change is audit-logged. No redeploy is required.

## 7. Notification History and Audit Log

- **Notification History** shows every send — scheduled or manual — with
  date, time, recipient, message type, and delivery status, visible the same
  day it happens. Filter by recipient, date range, or message type. A send
  to a Team or Recipient List/Channel expands into one row per individual
  recipient outcome, so a group send is auditable down to the person.
- **Audit Log** is an append-only record of every administrative action —
  directory changes, opt-in/opt-out changes, schedule changes, and logins —
  each entry recording who did it, when, and what changed. Nothing can be
  edited or deleted from it.

## 8. Where the data comes from

Sales, brand performance, and doctor/territory data are refreshed
automatically every night from the Source System (a nightly batch import,
not manual entry). Invalid records in a batch are rejected and logged
without blocking the valid records in the same batch. The Dashboard's
"Data as of" badge reflects the last successful import.

## 9. Key rules worth knowing

- **Consent-first delivery:** a recipient must have recorded WhatsApp
  opt-in consent before any message — scheduled or manual — reaches them.
- **Last-Administrator guard:** the sole remaining Administrator account
  can't be deleted or deactivated.
- **No free-form messages:** every WhatsApp send, manual or automated, uses
  a pre-approved template — this is a WhatsApp Business platform
  requirement, not a GrowthTrack limitation.
- **Soft deletes only:** removing a User, Team, or Recipient List/Channel
  never destroys history — it just stops future notifications from reaching
  it.
- **Everything administrative is audited:** directory CRUD, consent
  changes, schedule changes, and logins all leave an audit trail.
