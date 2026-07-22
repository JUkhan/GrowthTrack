"""message templates name unique index

Revision ID: b3f7a1c9d2e4
Revises: c4a8f21e6b3d
Create Date: 2026-07-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b3f7a1c9d2e4'
down_revision: Union[str, Sequence[str], None] = 'c4a8f21e6b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Story 4.5's MessageTemplateDirectoryService already app-level-checks
    # name uniqueness before insert/update, same as TeamDirectoryService/
    # RecipientListDirectoryService — this index closes the same small
    # concurrent-create race those two entities already accept, at
    # near-zero cost, since it wasn't closed for them from day one.
    op.create_index(
        "ix_message_templates_name_uq", "message_templates", ["name"], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_message_templates_name_uq", table_name="message_templates")
