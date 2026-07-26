"""Content-Disposition filename sanitization."""

from __future__ import annotations

from payroll_copilot.presentation.api.content_disposition import (
    sanitize_content_disposition_filename,
)


def test_preserves_normal_filename() -> None:
    assert sanitize_content_disposition_filename("payslip-2026-01.pdf") == "payslip-2026-01.pdf"


def test_strips_cr_lf_and_quotes() -> None:
    dirty = 'evil\r\nfilename="injected.pdf'
    cleaned = sanitize_content_disposition_filename(dirty)
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert '"' not in cleaned
    assert "evil" in cleaned


def test_strips_path_components() -> None:
    assert sanitize_content_disposition_filename("../../etc/passwd") == "passwd"
    assert sanitize_content_disposition_filename(r"..\secret\file.pdf") == "file.pdf"


def test_control_characters_removed() -> None:
    cleaned = sanitize_content_disposition_filename("a\x00b\x1fc.pdf")
    assert cleaned == "abc.pdf"


def test_empty_falls_back() -> None:
    assert sanitize_content_disposition_filename(None) == "document"
    assert sanitize_content_disposition_filename("   ") == "document"
    assert sanitize_content_disposition_filename('""') == "document"
