"""HTTP-boundary validation for n8n leave extraction payloads."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from payroll_copilot.presentation.api.routes.integrations import (
    InboundLeaveBatchRequest,
    InboundVacationRequest,
    LeaveExtractionPayload,
)


def test_valid_n8n_extraction_payload() -> None:
    payload = LeaveExtractionPayload.model_validate(
        {
            "employee_email": "ada@example.com",
            "employee_name": "Ada",
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
            "confidence": 0.92,
            "explanation": "clear dates",
        }
    )
    assert payload.employee_email == "ada@example.com"
    assert payload.confidence == pytest.approx(0.92)


def test_missing_optional_extraction_fields_ok() -> None:
    payload = LeaveExtractionPayload.model_validate({})
    assert payload.employee_email is None
    assert payload.confidence is None
    assert payload.start_date is None


def test_malformed_confidence_rejected() -> None:
    with pytest.raises(ValidationError):
        LeaveExtractionPayload.model_validate({"confidence": "high"})


def test_inbound_vacation_accepts_typed_extraction() -> None:
    body = InboundVacationRequest.model_validate(
        {
            "provider": "imap",
            "provider_message_id": "msg-1",
            "classification": "VACATION",
            "extraction": {
                "employee_email": "ada@example.com",
                "start_date": "2026-08-01",
                "end_date": "2026-08-02",
                "confidence": 0.88,
            },
        }
    )
    assert body.extraction.employee_email == "ada@example.com"
    assert body.extraction.confidence == pytest.approx(0.88)


def test_inbound_batch_rejects_malformed_confidence() -> None:
    with pytest.raises(ValidationError):
        InboundLeaveBatchRequest.model_validate(
            {
                "items": [
                    {
                        "provider": "imap",
                        "provider_message_id": "msg-1",
                        "classification": "SICK_LEAVE",
                        "extraction": {"confidence": "not-a-number"},
                    }
                ]
            }
        )


def test_inbound_batch_allows_empty_extraction() -> None:
    body = InboundLeaveBatchRequest.model_validate(
        {
            "items": [
                {
                    "provider": "imap",
                    "provider_message_id": "msg-2",
                    "classification": "VACATION",
                }
            ]
        }
    )
    assert body.items[0].extraction.confidence is None
