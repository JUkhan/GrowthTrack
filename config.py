"""Typed application configuration.

Single source of truth for environment-derived settings (Consistency
Conventions: "one typed settings object (pydantic-settings) ... no
scattered os.environ calls"). Every layer reads config through
``get_settings()`` instead of touching ``os.environ`` directly.
"""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field
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

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str

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
