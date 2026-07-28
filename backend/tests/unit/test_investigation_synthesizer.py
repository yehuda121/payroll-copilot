"""Unit tests for natural investigation synthesizer copy."""

from __future__ import annotations

from payroll_copilot.application.services.investigation_synthesizer import (
    clarification_no_history,
    resolve_response_locale,
    synthesize_explained,
)
from payroll_copilot.domain.investigation.types import (
    InvestigationFocus,
    LineItemDelta,
    PeriodRef,
)


def test_hebrew_message_forces_hebrew_even_when_locale_en() -> None:
    assert resolve_response_locale(message="למה ירד לי הנטו?", locale="en") == "he"


def test_synthesize_hebrew_is_natural_paragraph_not_raw_arrows() -> None:
    answer = synthesize_explained(
        locale="en",  # overridden by Hebrew message
        message="למה עלתה לי הפנסיה?",
        focus=InvestigationFocus.PENSION,
        target=PeriodRef(2026, 6),
        comparison=PeriodRef(2026, 5),
        deltas=[
            LineItemDelta(
                field_key="gross_salary",
                current_value="8854",
                prior_value="5212",
                absolute_delta="3642",
                direction="increased",
            ),
            LineItemDelta(
                field_key="pension_employee",
                current_value="620",
                prior_value="365",
                absolute_delta="255",
                direction="increased",
            ),
        ],
    )
    assert "→" not in answer
    assert "—" not in answer
    assert "יוני 2026" in answer
    assert "מאי 2026" in answer
    assert "₪" in answer
    assert "ברוטו" in answer
    assert "פנסיה" in answer
    assert "אחוז" in answer or "בהתאם" in answer


def test_missing_prior_month_is_friendly_hebrew() -> None:
    text = clarification_no_history(
        locale="en",
        message="למה ירד לי הנטו?",
        target=PeriodRef(2026, 6),
        expected_prior=PeriodRef(2026, 5),
    )
    assert "מאי 2026" in text
    assert "אינו זמין" in text or "לא זמין" in text
    assert "→" not in text
