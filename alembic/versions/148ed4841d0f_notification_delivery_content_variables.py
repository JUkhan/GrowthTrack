"""notification delivery content variables

Revision ID: 148ed4841d0f
Revises: 2f399b8b1526
Create Date: 2026-07-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '148ed4841d0f'
down_revision: Union[str, Sequence[str], None] = '2f399b8b1526'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Retrying a failed send means calling WhatsAppSender.send_template_message
    # again with the exact same content_variables used originally — but
    # nothing persists them today. Per-delivery-row (not per-Notification)
    # granularity works uniformly for Manual (identical content_variables
    # across every row of one Notification) and Scheduled (per-recipient
    # content_variables) sends (Story 4.3).
    op.add_column(
        "notification_deliveries",
        sa.Column(
            "content_variables", sa.JSON(), nullable=False, server_default="{}"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("notification_deliveries", "content_variables")
