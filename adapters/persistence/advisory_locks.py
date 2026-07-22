"""Fixed 32-bit keys for Postgres advisory locks (``pg_advisory_xact_lock``/
``pg_try_advisory_xact_lock``).

Every key used anywhere in this codebase must be listed here — a single
place to see the full set and guarantee none collide, rather than each call
site coordinating by code comment alone.
"""

BOOTSTRAP_LOCK_KEY = 890217364
"""First-run administrator bootstrap serialization (Story 1.2)."""

NIGHTLY_IMPORT_LOCK_KEY = 471028596
"""Nightly Source System import concurrency serialization (Story 2.1)."""

ADMINISTRATOR_REMOVAL_LOCK_KEY = 615349082
"""Last-Administrator deactivate/delete serialization (Story 3.1 code
review) — closes the count-then-act race Story 1.3's code review deferred
to this story."""

DAILY_REPORT_LOCK_KEY = 738104259
"""Daily Report scheduled-send concurrency serialization (Story 4.2) —
defense-in-depth against two scheduler processes/threads overlapping
within the same trigger window; the authoritative zero-duplicate-send
guarantee is AD-2's partial unique index on
(recipient_user_id, operational_day)."""
