"""Typed application configuration.

Single source of truth for environment-derived settings (Consistency
Conventions: "one typed settings object (pydantic-settings) ... no
scattered os.environ calls"). Every layer reads config through
``get_settings()`` instead of touching ``os.environ`` directly.
"""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _postgres_url(scheme: str, user: str, password: str, host: str, port: int, db: str) -> str:
    return f"{scheme}://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"

    # postgres_host defaults to "localhost" for host-based dev (e.g. against
    # a compose Postgres published on 127.0.0.1); containers override it to
    # "postgres", the compose service name.
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str
    postgres_migrator_user: str
    postgres_migrator_password: str
    postgres_app_user: str
    postgres_app_password: str

    jwt_signing_key: str
    # 8 hours by default; PRD leaves the exact TTL configurable (AD Deferred).
    # gt=0: a zero/negative value would issue already-expired tokens and an
    # immediately-deleted cookie, breaking login with no obvious cause.
    jwt_expiry_minutes: int = Field(default=480, gt=0)

    # OWASP-validated defaults (Blocking Brute Force Attacks / Authentication
    # Cheat Sheet): 3-10 attempts and ~15-20 minute lockouts are both typical.
    login_lockout_threshold: int = Field(default=5, gt=0)
    login_lockout_duration_minutes: int = Field(default=15, gt=0)
    # OWASP Forgot Password Cheat Sheet: reset tokens should expire within
    # roughly 15-60 minutes.
    password_reset_token_ttl_minutes: int = Field(default=60, gt=0)

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str

    # Exact public origin registered as this app's status-callback URL in
    # the Twilio console — required, no default (deployment-specific, like
    # twilio_account_sid). Twilio signs the exact POST URL it called; Nginx
    # doesn't forward the original scheme/host to the API container, so
    # `request.url` inside FastAPI would be the internal http:// URL, not
    # what Twilio actually signed. A mismatch here silently breaks
    # signature verification for every callback (Story 4.3).
    webhook_public_base_url: str

    # [ASSUMPTION — CONFIRM, PRD §13.12] Retry policy magnitude pending
    # business confirmation — 3 additional attempts with 1/5/15-minute
    # exponential backoff is this story's own placeholder default. Capped at
    # 3 (le=3) because list_retry_eligible's backoff query only has three
    # hardcoded branches, one per backoff_minutes_1/2/3 setting below — a
    # value above 3 would leave attempt_count 4+ rows permanently stuck in
    # FAILED_RETRYABLE, never matched by any branch. Raising this cap
    # requires adding a matching backoff_minutes_N setting and query branch
    # first. 0 is a valid, deliberately different operating mode: every
    # failure (sync or webhook-reported) is immediately terminal, with no
    # retry at all.
    notification_max_retry_attempts: int = Field(default=3, ge=0, le=3)
    notification_retry_backoff_minutes_1: int = Field(default=1, gt=0)
    notification_retry_backoff_minutes_2: int = Field(default=5, gt=0)
    notification_retry_backoff_minutes_3: int = Field(default=15, gt=0)
    notification_retry_poll_interval_seconds: int = Field(default=30, gt=0)

    # [ASSUMPTION — CONFIRM] File-drop CSV is this story's own placeholder
    # transport (PRD §13 Open Question #1 leaves the real Source System
    # unresolved) — must be confirmed with the business/ops stakeholder who
    # knows the real upstream system.
    source_system_import_dir: str = Field(default="/data/source_system/incoming")

    # [ASSUMPTION — CONFIRM] Neither the PRD nor the epics specify an exact
    # nightly time — only "every night". 19:30 UTC = 01:30 Asia/Dhaka
    # (UTC+6) is this story's own placeholder, same provisional status as
    # source_system_import_dir above, so it gets the same config escape
    # hatch rather than being a bare literal in scheduler/main.py.
    nightly_import_cron_hour: int = Field(default=19, ge=0, le=23)
    nightly_import_cron_minute: int = Field(default=30, ge=0, le=59)

    # [ASSUMPTION] Neither the PRD nor epics.md define the Dashboard's exact
    # "expected refresh window" (EXPERIENCE.md names the concept but not a
    # number). The nightly import runs once per day (Story 2.1); 24 hours is
    # this story's own placeholder — generous enough that a nightly job
    # running a little late doesn't flap the badge, tight enough that a
    # genuinely missed night is caught the next morning. Same
    # provisional-default treatment as source_system_import_dir/
    # nightly_import_cron_hour above — not a hard business-sign-off blocker
    # like AC #6's aggregation formula, just flagged for the record.
    dashboard_stale_after_hours: int = Field(default=24, gt=0)

    # [ASSUMPTION — CONFIRM, epics.md Story 2.3 AC #4 / PRD §4.3 footnote]
    # Neither the PRD nor epics.md define how many brands belong in each of
    # Top/Low-Performing/Focus — a business decision, not an engineering
    # call. 5/5/5 is this story's own placeholder default (see
    # domain/metrics.py's _classify_brands docstring for the full
    # reasoning). Must be confirmed by a business/product stakeholder
    # before this story is marked done — not a silent default.
    brand_top_n: int = Field(default=5, gt=0)
    brand_low_performing_n: int = Field(default=5, gt=0)
    brand_focus_n: int = Field(default=5, gt=0)

    # [ASSUMPTION — CONFIRM] The PRD states this exact default explicitly
    # (prd.md line 176: "the schedule is... [ASSUMPTION: default 07:00
    # Asia/Dhaka, pending confirmation — §13]") — more concrete than
    # nightly_import_cron_hour's own placeholder, but still flagged
    # pending since the PRD itself marks it unconfirmed. 01:00 UTC = 07:00
    # Asia/Dhaka (UTC+6). ReportSchedule (AD-11, DB-backed, Administrator-
    # editable) is Story 4.4's job — this is the same provisional
    # Settings-field-plus-.env-escape-hatch pattern as nightly_import_cron_*.
    report_send_cron_hour: int = Field(default=1, ge=0, le=23)
    report_send_cron_minute: int = Field(default=0, ge=0, le=59)

    # [ASSUMPTION — CONFIRM] No source document specifies a doctor-list
    # truncation count for the Daily Report (sample-whatsapp-report.md
    # shows 3, but its own note frames that as illustrative, not spec'd).
    # 5 for consistency with brand_top_n's default.
    report_top_doctors_n: int = Field(default=5, gt=0)

    @field_validator("source_system_import_dir")
    @classmethod
    def _source_system_import_dir_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_system_import_dir must not be blank")
        return value

    @property
    def database_url(self) -> str:
        """Runtime DML-only connection string (api/scheduler)."""
        return _postgres_url(
            "postgresql+asyncpg",
            self.postgres_app_user,
            self.postgres_app_password,
            self.postgres_host,
            self.postgres_port,
            self.postgres_db,
        )

    @property
    def database_migration_url(self) -> str:
        """Migration-capable (DDL) connection string (Alembic)."""
        return _postgres_url(
            "postgresql+psycopg",
            self.postgres_migrator_user,
            self.postgres_migrator_password,
            self.postgres_host,
            self.postgres_port,
            self.postgres_db,
        )


class MigrationSettings(BaseSettings):
    """DB-only settings for Alembic — migrations shouldn't require the
    unrelated JWT/Twilio fields ``Settings`` needs for the running app."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str
    postgres_migrator_user: str
    postgres_migrator_password: str

    @property
    def database_migration_url(self) -> str:
        return _postgres_url(
            "postgresql+psycopg",
            self.postgres_migrator_user,
            self.postgres_migrator_password,
            self.postgres_host,
            self.postgres_port,
            self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields are sourced from the environment


@lru_cache
def get_migration_settings() -> MigrationSettings:
    return MigrationSettings()  # type: ignore[call-arg]  # fields are sourced from the environment
