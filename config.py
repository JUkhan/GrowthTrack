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
