"""opt in consents

Revision ID: 1dfe4d12bdee
Revises: 976cabf50f32
Create Date: 2026-07-20 17:38:19.759081

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1dfe4d12bdee'
down_revision: Union[str, Sequence[str], None] = '976cabf50f32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "opt_in_consents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("mobile", sa.String(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opt_in_consents_user_id_active_uq",
        "opt_in_consents",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_opt_in_consents_user_id_active_uq", table_name="opt_in_consents")
    op.drop_table("opt_in_consents")
