"""recipient lists and membership

Revision ID: 976cabf50f32
Revises: 17eb25555c26
Create Date: 2026-07-20 16:16:50.261339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '976cabf50f32'
down_revision: Union[str, Sequence[str], None] = '17eb25555c26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "recipient_lists",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    # No column-level unique constraint on `name` — go straight to the
    # active-only partial index (code review of Story 3.1 only arrived at
    # this after a follow-up migration; this story's first migration gets
    # it right from the start).
    op.create_index(
        "ix_recipient_lists_name_active_uq",
        "recipient_lists",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # Pure join table (AD-4: relational join rows, never a JSON blob) — no
    # surrogate id/created_at, this table has no independent identity beyond
    # the (recipient_list_id, user_id) pair.
    op.create_table(
        "recipient_list_members",
        sa.Column("recipient_list_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["recipient_list_id"], ["recipient_lists.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("recipient_list_id", "user_id"),
    )
    op.create_index(
        "ix_recipient_list_members_user_id", "recipient_list_members", ["user_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Child before parent, same ordering discipline as dba27c6b09b6's
    # downgrade.
    op.drop_index("ix_recipient_list_members_user_id", "recipient_list_members")
    op.drop_table("recipient_list_members")

    op.drop_index("ix_recipient_lists_name_active_uq", "recipient_lists")
    op.drop_table("recipient_lists")
