"""recipients directory active-only uniqueness and team_id index

Revision ID: 17eb25555c26
Revises: dba27c6b09b6
Create Date: 2026-07-20 13:56:45.688359

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17eb25555c26'
down_revision: Union[str, Sequence[str], None] = 'dba27c6b09b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Code review of Story 3.1 (2026-07-20): the plain unique constraints on
    `users.mobile`/`teams.name` block reusing a soft-deleted record's
    mobile/name for a replacement (e.g. a departed Sales User's number
    reassigned to their successor), even though the domain layer only
    checks uniqueness against *active* rows. Swap both for partial unique
    indexes scoped to `status = 'active'` so an inactive row no longer
    reserves its mobile/name forever. Also adds the FK index on
    `users.team_id` that Story 3.1 introduced without one (Postgres does
    not auto-index FK columns, and this backs a lookup on every
    `GET /users`).
    """
    op.drop_constraint("uq_users_mobile", "users", type_="unique")
    op.create_index(
        "ix_users_mobile_active_uq",
        "users",
        ["mobile"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.drop_constraint("teams_name_key", "teams", type_="unique")
    op.create_index(
        "ix_teams_name_active_uq",
        "teams",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_index("ix_users_team_id", "users", ["team_id"])


def downgrade() -> None:
    """Downgrade schema.

    NOTE: recreating the plain unique constraints will fail if any two rows
    (active or inactive) share a mobile/name at downgrade time — a real
    possibility once this migration has been live and a mobile/name has
    been legitimately reused across an inactive and a new active row.
    Those rows must be reconciled by hand first. Deliberate consequence of
    the schema change, not an oversight (same posture as this migration
    chain's `dba27c6b09b6` downgrade note).
    """
    op.drop_index("ix_users_team_id", "users")

    op.drop_index("ix_teams_name_active_uq", "teams")
    op.create_unique_constraint("teams_name_key", "teams", ["name"])

    op.drop_index("ix_users_mobile_active_uq", "users")
    op.create_unique_constraint("uq_users_mobile", "users", ["mobile"])
