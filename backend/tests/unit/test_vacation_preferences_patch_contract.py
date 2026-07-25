"""Regression: preferences PATCH must accept notification_email (extra=forbid)."""

from __future__ import annotations

from pydantic import ValidationError

from payroll_copilot.presentation.api.routes.vacations import PreferencesPatch


def test_preferences_patch_accepts_notification_email_and_prefs() -> None:
    """FE always sends notification_email; forbidding it caused accountant save 422."""
    body = PreferencesPatch.model_validate(
        {
            "notification_email": "  HR@Example.COM ",
            "notify_on_new_vacation": False,
            "notify_on_error_or_attention": True,
        }
    )
    fields = body.model_dump(exclude_unset=True)
    assert fields["notification_email"] == "  HR@Example.COM "
    assert fields["notify_on_new_vacation"] is False
    assert fields["notify_on_error_or_attention"] is True
    assert "notification_email" in fields


def test_preferences_patch_accepts_null_notification_email_to_clear() -> None:
    body = PreferencesPatch.model_validate(
        {
            "notification_email": None,
            "notify_on_new_vacation": True,
            "notify_on_error_or_attention": True,
        }
    )
    fields = body.model_dump(exclude_unset=True)
    assert "notification_email" in fields
    assert fields["notification_email"] is None


def test_preferences_patch_still_forbids_unknown_fields() -> None:
    try:
        PreferencesPatch.model_validate({"notify_on_new_vacation": True, "imap_host": "evil"})
        raise AssertionError("expected ValidationError for unknown field")
    except ValidationError as exc:
        assert any(err.get("type") == "extra_forbidden" for err in exc.errors())
