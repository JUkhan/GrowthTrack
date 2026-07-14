#!/bin/sh
# Runs once, on first container start, via docker-entrypoint-initdb.d.
# POSTGRES_USER (the migration/DDL role) already exists and owns $POSTGRES_DB.
# This creates the least-privilege runtime (DML-only) role the api/scheduler
# containers use, per the Architecture spine's two-role convention.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE "${POSTGRES_APP_USER}" WITH LOGIN PASSWORD '${POSTGRES_APP_PASSWORD}';
    GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO "${POSTGRES_APP_USER}";
    GRANT USAGE ON SCHEMA public TO "${POSTGRES_APP_USER}";
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "${POSTGRES_APP_USER}";
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "${POSTGRES_APP_USER}";
    ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "${POSTGRES_APP_USER}";
    ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO "${POSTGRES_APP_USER}";
EOSQL
