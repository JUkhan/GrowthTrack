#!/bin/sh
# Runs once, on first container start, via docker-entrypoint-initdb.d.
# POSTGRES_USER (the migration/DDL role) already exists and owns $POSTGRES_DB.
# This creates:
#   - the least-privilege runtime (DML-only) role the api/scheduler
#     containers use, per the Architecture spine's two-role convention
#   - a read-only backup role, so the backup service never holds DDL rights
#
# Values are passed as psql -v variables (not shell-interpolated into the SQL
# text) so psql's :"ident"/:'literal' substitution handles quoting/escaping —
# a role name or password containing a quote character can't break the SQL.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v db="$POSTGRES_DB" \
    -v migrator_user="$POSTGRES_USER" \
    -v app_user="$POSTGRES_APP_USER" \
    -v app_password="$POSTGRES_APP_PASSWORD" \
    -v backup_user="$POSTGRES_BACKUP_USER" \
    -v backup_password="$POSTGRES_BACKUP_PASSWORD" <<-'EOSQL'
    CREATE ROLE :"app_user" WITH LOGIN PASSWORD :'app_password';
    GRANT CONNECT ON DATABASE :"db" TO :"app_user";
    GRANT USAGE ON SCHEMA public TO :"app_user";
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_user";
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_user";
    ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_user" IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
    ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_user" IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";

    CREATE ROLE :"backup_user" WITH LOGIN PASSWORD :'backup_password';
    GRANT CONNECT ON DATABASE :"db" TO :"backup_user";
    GRANT USAGE ON SCHEMA public TO :"backup_user";
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"backup_user";
    GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO :"backup_user";
    ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_user" IN SCHEMA public
        GRANT SELECT ON TABLES TO :"backup_user";
    ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_user" IN SCHEMA public
        GRANT SELECT ON SEQUENCES TO :"backup_user";
EOSQL
