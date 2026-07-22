from twilio.request_validator import RequestValidator

from adapters.whatsapp_twilio.webhook_verifier import categorize_message_status, verify_signature
from domain.models import WebhookOutcome

_URL = "https://growthtrack.example.com/webhooks/twilio/status"
_AUTH_TOKEN = "test-auth-token"
_PARAMS = {"MessageSid": "SM123", "MessageStatus": "delivered"}


def _sign(url: str = _URL, params: dict[str, str] = _PARAMS, auth_token: str = _AUTH_TOKEN) -> str:
    return RequestValidator(auth_token).compute_signature(url, params)


# --- verify_signature -----------------------------------------------------------


def test_verify_signature_accepts_a_signature_computed_by_the_sdk_itself():
    signature = _sign()

    assert verify_signature(_URL, _PARAMS, signature, _AUTH_TOKEN) is True


def test_verify_signature_rejects_a_tampered_param():
    signature = _sign()
    tampered_params = {**_PARAMS, "MessageStatus": "failed"}

    assert verify_signature(_URL, tampered_params, signature, _AUTH_TOKEN) is False


def test_verify_signature_rejects_the_wrong_auth_token():
    signature = _sign()

    assert verify_signature(_URL, _PARAMS, signature, "wrong-token") is False


# --- categorize_message_status ---------------------------------------------------


def test_categorize_message_status_maps_delivered_and_read_to_delivered():
    assert categorize_message_status("delivered") == WebhookOutcome.DELIVERED
    assert categorize_message_status("read") == WebhookOutcome.DELIVERED


def test_categorize_message_status_maps_failed_and_undelivered_to_failure():
    assert categorize_message_status("failed") == WebhookOutcome.FAILURE
    assert categorize_message_status("undelivered") == WebhookOutcome.FAILURE


def test_categorize_message_status_maps_queued_and_sent_to_none():
    assert categorize_message_status("queued") is None
    assert categorize_message_status("sent") is None


def test_categorize_message_status_maps_an_unrecognized_value_to_none_without_raising():
    assert categorize_message_status("some-future-twilio-status") is None
