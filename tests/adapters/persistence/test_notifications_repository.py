import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from adapters.persistence.database import create_session_factory
from adapters.persistence.notifications import (
    SqlAlchemyMessageTemplateRepository,
    SqlAlchemyNotificationDeliveryRepository,
    SqlAlchemyNotificationRepository,
)
from adapters.persistence.users import SqlAlchemyUserRepository
from domain.models import (
    DeliveryStatus,
    MessageTemplate,
    Notification,
    NotificationDelivery,
    NotificationTarget,
    NotificationType,
    Role,
    TargetType,
    User,
    UserStatus,
)


async def _seed_user(mobile: str) -> User:
    session_factory = create_session_factory()
    user = User(
        id=uuid.uuid4(),
        username=None,
        hashed_password=None,
        role=Role.SALES_USER,
        status=UserStatus.ACTIVE,
        version=1,
        created_at=datetime.now(UTC),
        name="Karim",
        mobile=mobile,
    )
    async with session_factory() as session:
        await SqlAlchemyUserRepository(session).add(user)
        await session.commit()
    return user


async def _seed_template(name: str = "Target Revision Notice") -> MessageTemplate:
    template = MessageTemplate(
        id=uuid.uuid4(),
        name=name,
        twilio_content_sid="HXabc123",
        variable_slots=["team_name", "new_target"],
        body_preview_template="{team_name}: {new_target}",
        created_at=datetime.now(UTC),
    )
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyMessageTemplateRepository(session).add(template)
        await session.commit()
    return template


async def _seed_notification(template_id: uuid.UUID, created_by_user_id: uuid.UUID) -> Notification:
    notification = Notification(
        id=uuid.uuid4(),
        notification_type=NotificationType.MANUAL,
        template_id=template_id,
        created_by_user_id=created_by_user_id,
        created_at=datetime.now(UTC),
    )
    session_factory = create_session_factory()
    async with session_factory() as session:
        await SqlAlchemyNotificationRepository(session).add(notification, [])
        await session.commit()
    return notification


def _delivery_row(
    notification_id: uuid.UUID,
    recipient_user_id: uuid.UUID,
    notification_type: NotificationType = NotificationType.MANUAL,
    operational_day=None,
    status: DeliveryStatus = DeliveryStatus.QUEUED,
) -> NotificationDelivery:
    now = datetime.now(UTC)
    return NotificationDelivery(
        id=uuid.uuid4(),
        notification_id=notification_id,
        notification_type=notification_type,
        recipient_user_id=recipient_user_id,
        operational_day=operational_day,
        status=status,
        attempt_count=0,
        provider_message_sid=None,
        failure_reason=None,
        created_at=now,
        updated_at=now,
    )


# --- SqlAlchemyMessageTemplateRepository ----------------------------------------


async def test_add_and_get_by_id_round_trips_a_template():
    template = await _seed_template("Round Trip Notice")

    session_factory = create_session_factory()
    async with session_factory() as session:
        found = await SqlAlchemyMessageTemplateRepository(session).get_by_id(template.id)

    assert found is not None
    assert found.name == "Round Trip Notice"
    assert found.variable_slots == ["team_name", "new_target"]


async def test_get_by_id_returns_none_for_an_unknown_id():
    session_factory = create_session_factory()
    async with session_factory() as session:
        found = await SqlAlchemyMessageTemplateRepository(session).get_by_id(uuid.uuid4())

    assert found is None


async def test_get_by_name_returns_none_for_an_unknown_name():
    session_factory = create_session_factory()
    async with session_factory() as session:
        found = await SqlAlchemyMessageTemplateRepository(session).get_by_name("Nonexistent")

    assert found is None


async def test_list_active_includes_a_seeded_template():
    template = await _seed_template("Listed Notice")

    session_factory = create_session_factory()
    async with session_factory() as session:
        templates = await SqlAlchemyMessageTemplateRepository(session).list_active()

    assert any(t.id == template.id for t in templates)


async def test_update_persists_every_field_and_returns_true():
    template = await _seed_template("Update Target Notice")
    session_factory = create_session_factory()

    async with session_factory() as session:
        updated = await SqlAlchemyMessageTemplateRepository(session).update(
            template.id,
            "Renamed Notice",
            "HXupdated",
            ["new_slot"],
            "{new_slot}",
        )
        await session.commit()

    assert updated is True

    async with session_factory() as session:
        found = await SqlAlchemyMessageTemplateRepository(session).get_by_id(template.id)

    assert found.name == "Renamed Notice"
    assert found.twilio_content_sid == "HXupdated"
    assert found.variable_slots == ["new_slot"]
    assert found.body_preview_template == "{new_slot}"


async def test_update_returns_false_for_an_unknown_id():
    session_factory = create_session_factory()
    async with session_factory() as session:
        updated = await SqlAlchemyMessageTemplateRepository(session).update(
            uuid.uuid4(), "Name", "HXabc", [], "Static body"
        )

    assert updated is False


async def test_name_unique_index_rejects_a_duplicate_template_name():
    await _seed_template("Duplicate Notice")

    with pytest.raises(IntegrityError):
        await _seed_template("Duplicate Notice")


# --- SqlAlchemyNotificationRepository --------------------------------------------


async def test_add_bundles_notification_and_target_rows_in_one_call():
    user = await _seed_user("+8801700000901")
    template = await _seed_template("Bundled Notice")
    notification = Notification(
        id=uuid.uuid4(),
        notification_type=NotificationType.MANUAL,
        template_id=template.id,
        created_by_user_id=user.id,
        created_at=datetime.now(UTC),
    )
    target = NotificationTarget(
        id=uuid.uuid4(),
        notification_id=notification.id,
        target_type=TargetType.USER,
        target_id=user.id,
    )
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyNotificationRepository(session).add(notification, [target])
        await session.commit()

    async with session_factory() as session:
        row = await session.execute(
            text("SELECT notification_type FROM notifications WHERE id = :id"),
            {"id": notification.id},
        )
        assert row.scalar_one() == "manual"

        target_row = await session.execute(
            text(
                "SELECT target_type, target_id FROM notification_targets "
                "WHERE notification_id = :id"
            ),
            {"id": notification.id},
        )
        target_type, target_id = target_row.one()
        assert target_type == "user"
        assert target_id == user.id


# --- SqlAlchemyNotificationDeliveryRepository ------------------------------------


async def test_bulk_create_persists_every_row():
    user_one = await _seed_user("+8801700000902")
    user_two = await _seed_user("+8801700000903")
    template = await _seed_template("Bulk Create Notice")
    notification = await _seed_notification(template.id, user_one.id)
    rows = [
        _delivery_row(notification.id, user_one.id),
        _delivery_row(notification.id, user_two.id),
    ]
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyNotificationDeliveryRepository(session).bulk_create(rows)
        await session.commit()

    async with session_factory() as session:
        count = await session.execute(
            text("SELECT COUNT(*) FROM notification_deliveries WHERE notification_id = :id"),
            {"id": notification.id},
        )
        assert count.scalar_one() == 2


async def test_claim_for_dispatch_transitions_queued_to_sending_and_returns_true_once():
    user = await _seed_user("+8801700000904")
    template = await _seed_template("Claim Notice")
    notification = await _seed_notification(template.id, user.id)
    row = _delivery_row(notification.id, user.id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyNotificationDeliveryRepository(session).bulk_create([row])
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyNotificationDeliveryRepository(session)
        first = await repo.claim_for_dispatch(row.id)
        second = await repo.claim_for_dispatch(row.id)
        await session.commit()

    assert first is True
    assert second is False

    async with session_factory() as session:
        status = await session.execute(
            text("SELECT status FROM notification_deliveries WHERE id = :id"), {"id": row.id}
        )
        assert status.scalar_one() == "sending"


async def test_claim_for_dispatch_returns_false_for_an_unknown_id():
    session_factory = create_session_factory()
    async with session_factory() as session:
        claimed = await SqlAlchemyNotificationDeliveryRepository(session).claim_for_dispatch(
            uuid.uuid4()
        )

    assert claimed is False


async def test_update_after_send_persists_status_sid_reason_and_increments_attempt_count():
    user = await _seed_user("+8801700000905")
    template = await _seed_template("Update Notice")
    notification = await _seed_notification(template.id, user.id)
    row = _delivery_row(notification.id, user.id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyNotificationDeliveryRepository(session).bulk_create([row])
        await session.commit()

    async with session_factory() as session:
        await SqlAlchemyNotificationDeliveryRepository(session).update_after_send(
            row.id, DeliveryStatus.SENDING, "SM-123", None
        )
        await session.commit()

    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT status, provider_message_sid, attempt_count FROM notification_deliveries "
                "WHERE id = :id"
            ),
            {"id": row.id},
        )
        status, sid, attempt_count = result.one()
        assert status == "sending"
        assert sid == "SM-123"
        assert attempt_count == 1


async def test_most_recent_status_summary_is_worst_status_among_that_notifications_deliveries():
    user_one = await _seed_user("+8801700000906")
    user_two = await _seed_user("+8801700000916")
    template = await _seed_template("Summary Notice")
    notification = await _seed_notification(template.id, user_one.id)
    succeeded = _delivery_row(notification.id, user_one.id)
    failed = _delivery_row(notification.id, user_two.id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        repo = SqlAlchemyNotificationDeliveryRepository(session)
        await repo.bulk_create([succeeded, failed])
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyNotificationDeliveryRepository(session)
        await repo.update_after_send(succeeded.id, DeliveryStatus.SENDING, "SM-1", None)
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyNotificationDeliveryRepository(session)
        await repo.update_after_send(failed.id, DeliveryStatus.FAILED, None, "21610: opted out")
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyNotificationDeliveryRepository(session)
        summary = await repo.most_recent_status_summary()

    # One recipient succeeded and one failed within the same (only)
    # Notification — the failure must not be hidden by the success, nor
    # vice versa (AC #8).
    assert summary is not None
    assert summary.status == DeliveryStatus.FAILED


async def test_most_recent_status_summary_is_scoped_to_the_latest_notification_only():
    user = await _seed_user("+8801700000917")
    template = await _seed_template("Scoped Summary Notice")
    session_factory = create_session_factory()

    older_notification = Notification(
        id=uuid.uuid4(),
        notification_type=NotificationType.MANUAL,
        template_id=template.id,
        created_by_user_id=user.id,
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    newer_notification = Notification(
        id=uuid.uuid4(),
        notification_type=NotificationType.MANUAL,
        template_id=template.id,
        created_by_user_id=user.id,
        created_at=datetime(2026, 7, 21, tzinfo=UTC),
    )
    async with session_factory() as session:
        await SqlAlchemyNotificationRepository(session).add(older_notification, [])
        await SqlAlchemyNotificationRepository(session).add(newer_notification, [])
        await session.commit()

    # The older Notification's only delivery is a failure; the newer
    # Notification's only delivery succeeds. The aggregate must reflect the
    # newer Notification alone, not the worst status across both.
    older_delivery = _delivery_row(older_notification.id, user.id)
    newer_delivery = _delivery_row(newer_notification.id, user.id)
    async with session_factory() as session:
        repo = SqlAlchemyNotificationDeliveryRepository(session)
        await repo.bulk_create([older_delivery, newer_delivery])
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyNotificationDeliveryRepository(session)
        await repo.update_after_send(older_delivery.id, DeliveryStatus.FAILED, None, "boom")
        await repo.update_after_send(newer_delivery.id, DeliveryStatus.SENDING, "SM-2", None)
        await session.commit()

    async with session_factory() as session:
        repo = SqlAlchemyNotificationDeliveryRepository(session)
        summary = await repo.most_recent_status_summary()

    assert summary is not None
    assert summary.status == DeliveryStatus.SENDING


async def test_most_recent_status_summary_returns_none_when_the_table_is_empty():
    session_factory = create_session_factory()
    async with session_factory() as session:
        repo = SqlAlchemyNotificationDeliveryRepository(session)
        summary = await repo.most_recent_status_summary()

    assert summary is None


# --- Partial unique indexes (AD-2) -----------------------------------------------


async def test_manual_partial_unique_index_rejects_a_duplicate_notification_recipient_pair():
    user = await _seed_user("+8801700000907")
    template = await _seed_template("Duplicate Manual Notice")
    notification = await _seed_notification(template.id, user.id)
    row = _delivery_row(notification.id, user.id)
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyNotificationDeliveryRepository(session).bulk_create([row])
        await session.commit()

    with pytest.raises(IntegrityError):
        async with session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO notification_deliveries "
                    "(id, notification_id, notification_type, recipient_user_id, "
                    "operational_day, status, attempt_count, created_at, updated_at) "
                    "VALUES (:id, :notification_id, 'manual', :recipient_user_id, NULL, "
                    "'queued', 0, now(), now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "notification_id": notification.id,
                    "recipient_user_id": user.id,
                },
            )
            await session.commit()


async def test_scheduled_partial_unique_index_allows_the_same_recipient_a_manual_row_already_used():
    user = await _seed_user("+8801700000908")
    template = await _seed_template("Cross Type Notice")
    notification = await _seed_notification(template.id, user.id)
    manual_row = _delivery_row(notification.id, user.id, notification_type=NotificationType.MANUAL)
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyNotificationDeliveryRepository(session).bulk_create([manual_row])
        await session.commit()

    # A scheduled-type row for the SAME recipient_user_id must not collide
    # with the manual row above — the two partial indexes are scoped by
    # notification_type, never a single composite constraint (AD-2).
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO notification_deliveries "
                "(id, notification_id, notification_type, recipient_user_id, "
                "operational_day, status, attempt_count, created_at, updated_at) "
                "VALUES (:id, :notification_id, 'scheduled', :recipient_user_id, :day, "
                "'queued', 0, now(), now())"
            ),
            {
                "id": uuid.uuid4(),
                "notification_id": notification.id,
                "recipient_user_id": user.id,
                "day": datetime.now(UTC).date(),
            },
        )
        await session.commit()

    async with session_factory() as session:
        count = await session.execute(
            text(
                "SELECT COUNT(*) FROM notification_deliveries WHERE recipient_user_id = :id"
            ),
            {"id": user.id},
        )
        assert count.scalar_one() == 2


# --- AC #7: manual send rows are queryable and correctly tagged -----------------


async def test_try_acquire_daily_report_lock_succeeds_when_uncontended():
    session_factory = create_session_factory()
    async with session_factory() as session:
        acquired = await SqlAlchemyNotificationRepository(session).try_acquire_daily_report_lock()
        await session.commit()

    assert acquired is True


async def test_try_acquire_daily_report_lock_fails_when_another_transaction_already_holds_it():
    session_factory = create_session_factory()
    async with session_factory() as holder_session:
        holder_acquired = await SqlAlchemyNotificationRepository(
            holder_session
        ).try_acquire_daily_report_lock()
        assert holder_acquired is True

        async with session_factory() as contender_session:
            contender_acquired = await SqlAlchemyNotificationRepository(
                contender_session
            ).try_acquire_daily_report_lock()

        assert contender_acquired is False
        await holder_session.commit()


async def test_scheduled_partial_unique_index_rejects_a_same_day_duplicate_for_the_same_recipient():
    user = await _seed_user("+8801700000918")
    template = await _seed_template("Duplicate Scheduled Notice")
    notification = await _seed_notification(template.id, user.id)
    today = datetime.now(UTC).date()
    row = _delivery_row(
        notification.id,
        user.id,
        notification_type=NotificationType.SCHEDULED,
        operational_day=today,
    )
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyNotificationDeliveryRepository(session).bulk_create([row])
        await session.commit()

    with pytest.raises(IntegrityError):
        async with session_factory() as session:
            duplicate = _delivery_row(
                notification.id,
                user.id,
                notification_type=NotificationType.SCHEDULED,
                operational_day=today,
            )
            await SqlAlchemyNotificationDeliveryRepository(session).bulk_create([duplicate])
            await session.commit()


async def test_bulk_create_rolls_back_so_the_session_stays_usable_after_a_caught_duplicate():
    # Regression test (code review): a failed flush leaves an AsyncSession's
    # transaction unusable for any further statement until it's rolled
    # back — bulk_create must roll back internally before re-raising, or a
    # caller that catches the IntegrityError (exactly what
    # ScheduledReportService.run_daily_report does for AC #4) would still
    # crash on its own next statement (e.g. the caller's session.commit()).
    user = await _seed_user("+8801700000919")
    template = await _seed_template("Duplicate Scheduled Notice Rollback")
    notification = await _seed_notification(template.id, user.id)
    today = datetime.now(UTC).date()
    row = _delivery_row(
        notification.id,
        user.id,
        notification_type=NotificationType.SCHEDULED,
        operational_day=today,
    )
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyNotificationDeliveryRepository(session).bulk_create([row])
        await session.commit()

    async with session_factory() as session:
        duplicate = _delivery_row(
            notification.id,
            user.id,
            notification_type=NotificationType.SCHEDULED,
            operational_day=today,
        )
        with pytest.raises(IntegrityError):
            await SqlAlchemyNotificationDeliveryRepository(session).bulk_create([duplicate])

        # If bulk_create hadn't rolled back internally, this would raise
        # PendingRollbackError instead of completing normally.
        acquired = await SqlAlchemyNotificationRepository(session).try_acquire_daily_report_lock()
        assert acquired is True
        await session.commit()


async def test_a_completed_manual_sends_rows_carry_notification_type_manual_and_are_queryable():
    user = await _seed_user("+8801700000909")
    template = await _seed_template("AC7 Notice")
    notification = await _seed_notification(template.id, user.id)
    row = _delivery_row(notification.id, user.id, status=DeliveryStatus.SENDING)
    session_factory = create_session_factory()

    async with session_factory() as session:
        await SqlAlchemyNotificationDeliveryRepository(session).bulk_create([row])
        await session.commit()

    async with session_factory() as session:
        notification_type = await session.execute(
            text("SELECT notification_type FROM notifications WHERE id = :id"),
            {"id": notification.id},
        )
        assert notification_type.scalar_one() == "manual"

        delivery_type = await session.execute(
            text("SELECT notification_type FROM notification_deliveries WHERE id = :id"),
            {"id": row.id},
        )
        assert delivery_type.scalar_one() == "manual"
