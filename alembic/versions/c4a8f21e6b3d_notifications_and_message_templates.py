"""notifications and message templates

Revision ID: c4a8f21e6b3d
Revises: 1dfe4d12bdee
Create Date: 2026-07-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a8f21e6b3d'
down_revision: Union[str, Sequence[str], None] = '1dfe4d12bdee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "message_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("twilio_content_sid", sa.String(), nullable=False),
        sa.Column("variable_slots", sa.JSON(), nullable=False),
        sa.Column("body_preview_template", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("notification_type", sa.String(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["message_templates.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Relational join rows, never a JSON blob (AD-4): one polymorphic
    # target_id column + a target_type discriminator, not per-type FK columns.
    op.create_table(
        "notification_targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("notification_id", sa.UUID(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_targets_notification_id", "notification_targets", ["notification_id"]
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("notification_id", sa.UUID(), nullable=False),
        # Denormalized onto the delivery row so the partial-unique-index
        # predicates below don't need to reference a joined table (AD-2).
        sa.Column("notification_type", sa.String(), nullable=False),
        sa.Column("recipient_user_id", sa.UUID(), nullable=False),
        sa.Column("operational_day", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_message_sid", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"]),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Two partial unique indexes, one per notification_type — never a single
    # composite constraint over nullable columns, since NULL-is-distinct-
    # from-NULL would defeat it (AD-2).
    op.create_index(
        "ix_notification_deliveries_manual_uq",
        "notification_deliveries",
        ["notification_id", "recipient_user_id"],
        unique=True,
        postgresql_where=sa.text("notification_type = 'manual'"),
    )
    op.create_index(
        "ix_notification_deliveries_scheduled_uq",
        "notification_deliveries",
        ["recipient_user_id", "operational_day"],
        unique=True,
        postgresql_where=sa.text("notification_type = 'scheduled'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Child before parent, same ordering discipline as prior migrations.
    op.drop_index("ix_notification_deliveries_scheduled_uq", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_manual_uq", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")

    op.drop_index("ix_notification_targets_notification_id", table_name="notification_targets")
    op.drop_table("notification_targets")

    op.drop_table("notifications")

    op.drop_table("message_templates")
