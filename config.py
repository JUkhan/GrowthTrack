"""Typed application configuration.

Single source of truth for environment-derived settings (Consistency
Conventions: "one typed settings object (pydantic-settings) ... no
scattered os.environ calls"). Every layer reads config through
``get_settings()`` instead of touching ``os.environ`` directly.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str

    @property
    def database_url(self) -> str:
        """Runtime DML-only connection string (api/scheduler)."""
        return (
            f"postgresql+asyncpg://{self.postgres_app_user}:{self.postgres_app_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_migration_url(self) -> str:
        """Migration-capable (DDL) connection string (Alembic)."""
        return (
            f"postgresql+psycopg://{self.postgres_migrator_user}:{self.postgres_migrator_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields are sourced from the environment
