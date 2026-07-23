"""report schedule

Revision ID: 7d3e9c2a5f81
Revises: 148ed4841d0f
Create Date: 2026-07-23 09:00:00.000000

"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d3e9c2a5f81'
down_revision: Union[str, Sequence[str], None] = '148ed4841d0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed, well-known id for the one-and-only ReportSchedule row (Story 4.4) —
# mirrored in domain/models.py's REPORT_SCHEDULE_ID constant. Never invent a
# second constant elsewhere; import this one.
REPORT_SCHEDULE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "report_schedules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("send_hour_utc", sa.SmallInteger(), nullable=False),
        sa.Column("send_minute_utc", sa.SmallInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Nullable: the seeded default row's initial value has no human
        # actor — mirrors Notification.created_by_user_id's existing
        # nullable-FK precedent (adapters/persistence/notifications.py).
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Singleton row, seeded here (not lazily by the service) so
    # GET /settings/report-schedule never 404s or needs get-or-create
    # branching — a row always exists from the moment this migration runs.
    # 01:00 UTC = 07:00 Asia/Dhaka, the same default config.py's retiring
    # report_send_cron_hour/minute already use. A fixed literal timestamp
    # (not sa.func.now()) — op.bulk_insert's executemany-style parameter
    # binding doesn't reliably support per-row SQL expressions.
    op.bulk_insert(
        sa.table(
            "report_schedules",
            sa.column("id", sa.UUID()),
            sa.column("send_hour_utc", sa.SmallInteger()),
            sa.column("send_minute_utc", sa.SmallInteger()),
            sa.column("updated_at", sa.DateTime(timezone=True)),
            sa.column("updated_by_user_id", sa.UUID()),
        ),
        [
            {
                "id": REPORT_SCHEDULE_ID,
                "send_hour_utc": 1,
                "send_minute_utc": 0,
                "updated_at": datetime(2026, 7, 23, tzinfo=UTC),
                "updated_by_user_id": None,
            }
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("report_schedules")
