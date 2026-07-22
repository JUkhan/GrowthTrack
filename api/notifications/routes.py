"""Manual Notification compose/send + message template listing (Story 4.1,
CAP-4).

Every route depends on ``get_current_user`` (AD-8's shared choke-point —
never an inline per-route check).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.audit_log import SqlAlchemyAuditLogRepository
from adapters.persistence.consent import SqlAlchemyOptInConsentRepository
from adapters.persistence.notifications import (
    SqlAlchemyMessageTemplateRepository,
    SqlAlchemyNotificationDeliveryRepository,
    SqlAlchemyNotificationRepository,
)
from adapters.persistence.recipient_lists import SqlAlchemyRecipientListRepository
from adapters.persistence.teams import SqlAlchemyTeamRepository
from adapters.persistence.users import SqlAlchemyUserRepository
from adapters.whatsapp_twilio.sender import TwilioWhatsAppSender
from api.auth.dependencies import get_current_user, get_db
from domain.models import MessageTemplate, User
from domain.notifications import (
    InvalidTemplateFields,
    InvalidVariableValues,
    ManualNotificationService,
    MessageTemplateDirectoryService,
    NoRecipientsSelected,
    RecipientResolutionService,
    TemplateNameTaken,
    TemplateNotFound,
)
from ports.whatsapp import WhatsAppSender

message_templates_router = APIRouter(prefix="/message-templates", tags=["notifications"])
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])


# Own dependency-provider function (not hardcoded inline in the route) so
# tests can override it with a fake sender rather than hitting real Twilio.
def get_whatsapp_sender() -> WhatsAppSender:
    return TwilioWhatsAppSender()


class MessageTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    twilio_content_sid: str
    variable_slots: list[str]
    body_preview_template: str


class MessageTemplateWriteRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    twilio_content_sid: str = Field(min_length=1, max_length=255)
    variable_slots: list[Annotated[str, Field(max_length=255)]] = Field(
        default_factory=list, max_length=20
    )
    body_preview_template: str = Field(min_length=1, max_length=2000)


CreateMessageTemplateRequest = MessageTemplateWriteRequest
UpdateMessageTemplateRequest = MessageTemplateWriteRequest


class ResolveRecipientsRequest(BaseModel):
    user_ids: list[uuid.UUID] = Field(default_factory=list)
    team_ids: list[uuid.UUID] = Field(default_factory=list)
    recipient_list_ids: list[uuid.UUID] = Field(default_factory=list)


class ResolveRecipientsResponse(BaseModel):
    selected_count: int
    unique_count: int
    overlap_count: int
    ineligible_count: int


class ComposeNotificationRequest(BaseModel):
    template_id: uuid.UUID
    variable_values: dict[str, str]
    user_ids: list[uuid.UUID] = Field(default_factory=list)
    team_ids: list[uuid.UUID] = Field(default_factory=list)
    recipient_list_ids: list[uuid.UUID] = Field(default_factory=list)


class DeliveryOutcomeResponse(BaseModel):
    recipient_user_id: uuid.UUID
    status: str
    failure_reason: str | None


class ComposeNotificationResponse(BaseModel):
    notification_id: uuid.UUID
    outcomes: list[DeliveryOutcomeResponse]


def _no_recipients_selected() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "no_recipients_selected",
            "message": "Select at least one recipient",
            "details": None,
        },
    )


def _invalid_variable_values() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "invalid_variable_values",
            "message": "The message's variable values don't match the template's variable slots",
            "details": None,
        },
    )


def _template_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "not_found",
            "message": "No MessageTemplate found for the given id",
            "details": None,
        },
    )


def _template_name_taken() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "template_name_taken",
            "message": "A message template with this name already exists",
            "details": None,
        },
    )


def _invalid_template_fields() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "invalid_template_fields",
            "message": "Name, Content SID, preview text, and every variable slot must be non-blank",
            "details": None,
        },
    )


def _to_message_template_response(template: MessageTemplate) -> MessageTemplateResponse:
    return MessageTemplateResponse(
        id=template.id,
        name=template.name,
        twilio_content_sid=template.twilio_content_sid,
        variable_slots=template.variable_slots,
        body_preview_template=template.body_preview_template,
    )


@message_templates_router.get("", response_model=list[MessageTemplateResponse])
async def list_message_templates(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[MessageTemplateResponse]:
    templates = SqlAlchemyMessageTemplateRepository(session)
    return [_to_message_template_response(template) for template in await templates.list_active()]


@message_templates_router.post(
    "", response_model=MessageTemplateResponse, status_code=status.HTTP_201_CREATED
)
async def create_message_template(
    body: CreateMessageTemplateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageTemplateResponse:
    templates = SqlAlchemyMessageTemplateRepository(session)
    service = MessageTemplateDirectoryService(templates, SqlAlchemyAuditLogRepository(session))

    try:
        template = await service.create_template(
            name=body.name,
            twilio_content_sid=body.twilio_content_sid,
            variable_slots=body.variable_slots,
            body_preview_template=body.body_preview_template,
            actor_user_id=current_user.id,
        )
    except TemplateNameTaken:
        await session.commit()
        raise _template_name_taken() from None
    except InvalidTemplateFields:
        await session.commit()
        raise _invalid_template_fields() from None

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _template_name_taken() from None

    return _to_message_template_response(template)


@message_templates_router.patch("/{template_id}", response_model=MessageTemplateResponse)
async def update_message_template(
    template_id: uuid.UUID,
    body: UpdateMessageTemplateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageTemplateResponse:
    templates = SqlAlchemyMessageTemplateRepository(session)
    service = MessageTemplateDirectoryService(templates, SqlAlchemyAuditLogRepository(session))

    try:
        template = await service.update_template(
            template_id=template_id,
            name=body.name,
            twilio_content_sid=body.twilio_content_sid,
            variable_slots=body.variable_slots,
            body_preview_template=body.body_preview_template,
            actor_user_id=current_user.id,
        )
    except TemplateNotFound:
        await session.commit()
        raise _template_not_found() from None
    except TemplateNameTaken:
        await session.commit()
        raise _template_name_taken() from None
    except InvalidTemplateFields:
        await session.commit()
        raise _invalid_template_fields() from None
    except IntegrityError:
        # Unlike create's INSERT (deferred to session.commit()), update()
        # executes its UPDATE eagerly via session.execute() — a concurrent-
        # rename race hits the unique-name index here, not at the commit
        # below.
        await session.rollback()
        raise _template_name_taken() from None

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _template_name_taken() from None

    return _to_message_template_response(template)


@notifications_router.post("/resolve-recipients", response_model=ResolveRecipientsResponse)
async def resolve_recipients(
    body: ResolveRecipientsRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ResolveRecipientsResponse:
    service = RecipientResolutionService(
        SqlAlchemyUserRepository(session),
        SqlAlchemyRecipientListRepository(session),
        SqlAlchemyOptInConsentRepository(session),
        SqlAlchemyTeamRepository(session),
    )
    resolved = await service.resolve(body.user_ids, body.team_ids, body.recipient_list_ids)
    return ResolveRecipientsResponse(
        selected_count=resolved.selected_count,
        unique_count=resolved.unique_count,
        overlap_count=resolved.overlap_count,
        ineligible_count=resolved.ineligible_count,
    )


@notifications_router.post(
    "", response_model=ComposeNotificationResponse, status_code=status.HTTP_201_CREATED
)
async def compose_and_send_notification(
    body: ComposeNotificationRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    whatsapp: WhatsAppSender = Depends(get_whatsapp_sender),
) -> ComposeNotificationResponse:
    users = SqlAlchemyUserRepository(session)
    resolution = RecipientResolutionService(
        users,
        SqlAlchemyRecipientListRepository(session),
        SqlAlchemyOptInConsentRepository(session),
        SqlAlchemyTeamRepository(session),
    )
    service = ManualNotificationService(
        templates=SqlAlchemyMessageTemplateRepository(session),
        notifications=SqlAlchemyNotificationRepository(session),
        deliveries=SqlAlchemyNotificationDeliveryRepository(session),
        users=users,
        whatsapp=whatsapp,
        resolution=resolution,
        audit_log=SqlAlchemyAuditLogRepository(session),
    )

    try:
        result = await service.compose_and_send(
            template_id=body.template_id,
            variable_values=body.variable_values,
            user_ids=body.user_ids,
            team_ids=body.team_ids,
            recipient_list_ids=body.recipient_list_ids,
            actor_user_id=current_user.id,
        )
    except TemplateNotFound:
        await session.commit()
        raise _template_not_found() from None
    except InvalidVariableValues:
        await session.commit()
        raise _invalid_variable_values() from None
    except NoRecipientsSelected:
        await session.commit()
        raise _no_recipients_selected() from None

    await session.commit()

    return ComposeNotificationResponse(
        notification_id=result.notification_id,
        outcomes=[
            DeliveryOutcomeResponse(
                recipient_user_id=outcome.recipient_user_id,
                status=outcome.status.value,
                failure_reason=outcome.failure_reason,
            )
            for outcome in result.outcomes
        ],
    )
