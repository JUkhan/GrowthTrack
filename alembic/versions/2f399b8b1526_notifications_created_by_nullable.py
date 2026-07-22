"""notifications created_by_user_id nullable

Revision ID: 2f399b8b1526
Revises: b3f7a1c9d2e4
Create Date: 2026-07-22 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2f399b8b1526'
down_revision: Union[str, Sequence[str], None] = 'b3f7a1c9d2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A Scheduled Notification (Story 4.2) is a system-triggered background
    # job with no human actor — mirrors dba27c6b09b6's identical
    # nullable-for-a-no-actor-case precedent (users.username/hashed_password).
    op.alter_column("notifications", "created_by_user_id", nullable=True)


def downgrade() -> None:
    """Downgrade schema.

    NOTE: reverting to nullable=False will fail if any Scheduled
    Notification row (created_by_user_id NULL) still exists — those rows
    must be removed first, same deliberate consequence dba27c6b09b6's
    downgrade already documents for its own nullable-relaxation.
    """
    op.alter_column("notifications", "created_by_user_id", nullable=False)
