"""recipient directory users and teams

Revision ID: dba27c6b09b6
Revises: e054c35b938f
Create Date: 2026-07-20 12:25:33.634458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dba27c6b09b6'
down_revision: Union[str, Sequence[str], None] = 'e054c35b938f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # `users` was built in Epic 1 exclusively for Administrator portal login
    # (username/hashed_password both NOT NULL). Story 3.1 needs the same
    # table to also hold Sales User/Manager roster entries that never
    # authenticate to the portal (Addendum A5) and so have neither — relax
    # both columns instead of splitting into two tables.
    op.alter_column("users", "username", nullable=True)
    op.alter_column("users", "hashed_password", nullable=True)
    # name/mobile/team_id stay DB-nullable — existing Administrator rows
    # keep them NULL forever; required-ness for Sales User/Manager is
    # enforced at the domain-service layer (domain/recipients.py), not the
    # schema. This sidesteps a backfill migration entirely (no sensible
    # default name/mobile value exists for existing Administrator rows).
    # Postgres treats NULL as distinct-from-NULL in a plain UNIQUE
    # constraint, so multiple Administrators with mobile IS NULL don't
    # collide — no partial/filtered index needed.
    op.add_column("users", sa.Column("name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("mobile", sa.String(), nullable=True))
    op.add_column("users", sa.Column("team_id", sa.UUID(), nullable=True))
    op.create_unique_constraint("uq_users_mobile", "users", ["mobile"])
    op.create_foreign_key("fk_users_team_id_teams", "users", "teams", ["team_id"], ["id"])

    # `teams` — adapters/persistence/teams.py's own docstring flagged this
    # debt: "full CRUD (soft-delete status, optimistic-concurrency version
    # column, management UI) is Epic 3 Story 3.1's job." server_default (not
    # just a Python-side dataclass default) is required so
    # get_or_create_by_name's existing raw INSERT (Story 2.1's nightly
    # ingestion, untouched by this story) keeps working without
    # modification — Postgres fills status/version from the column default
    # when the INSERT omits them, same reasoning 8ae7e5d0d8c9's
    # failed_login_count migration already documents.
    op.add_column(
        "teams", sa.Column("status", sa.String(), nullable=False, server_default="active")
    )
    op.add_column(
        "teams", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )


def downgrade() -> None:
    """Downgrade schema.

    NOTE: `alter_column` back to `nullable=False` on `username`/
    `hashed_password` will fail if any Sales User/Manager row created by
    this story (username/hashed_password both NULL) still exists at
    downgrade time — those rows must be removed first. This is a deliberate
    consequence of the schema this story introduces, not an oversight.
    """
    op.drop_column("teams", "version")
    op.drop_column("teams", "status")

    op.drop_constraint("fk_users_team_id_teams", "users", type_="foreignkey")
    op.drop_constraint("uq_users_mobile", "users", type_="unique")
    op.drop_column("users", "team_id")
    op.drop_column("users", "mobile")
    op.drop_column("users", "name")
    op.alter_column("users", "hashed_password", nullable=False)
    op.alter_column("users", "username", nullable=False)
