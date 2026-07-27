"""Content-Disposition filename sanitization and Unicode-safe headers."""

from __future__ import annotations

from starlette.responses import Response

from payroll_copilot.presentation.api.content_disposition import (
    build_content_disposition,
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


def test_build_ascii_filename_compatible() -> None:
    header = build_content_disposition("payslip-2026-01.pdf")
    assert header == 'inline; filename="payslip-2026-01.pdf"'
    header.encode("latin-1")
    Response(content=b"ok", headers={"Content-Disposition": header})


def test_build_hebrew_filename_latin1_safe() -> None:
    header = build_content_disposition("ינואר 2020.pdf")
    header.encode("latin-1")
    assert 'filename="' in header
    assert "filename*=UTF-8''" in header
    assert "\r" not in header and "\n" not in header
    # Starlette must accept the header without UnicodeEncodeError.
    response = Response(content=b"%PDF", media_type="application/pdf", headers={"Content-Disposition": header})
    assert response.headers["content-disposition"] == header


def test_build_arabic_filename_latin1_safe() -> None:
    header = build_content_disposition("قسيمة_الراتب.pdf")
    header.encode("latin-1")
    assert "filename*=UTF-8''" in header
    Response(content=b"%PDF", headers={"Content-Disposition": header})


def test_build_rejects_header_injection() -> None:
    dirty = 'evil\r\nSet-Cookie: x=1\nfilename="x.pdf'
    header = build_content_disposition(dirty)
    assert "\r" not in header
    assert "\n" not in header
    # CR/LF cannot split the header into additional HTTP header lines.
    assert header.count("Content-Disposition") == 0
    header.encode("latin-1")
    Response(content=b"ok", headers={"Content-Disposition": header})


def test_build_strips_quotes_in_filename_param() -> None:
    header = build_content_disposition('report "Q1".pdf')
    assert '"' not in sanitize_content_disposition_filename('report "Q1".pdf')
    assert header.startswith("inline; filename=")
    header.encode("latin-1")
    Response(content=b"ok", headers={"Content-Disposition": header})


def test_employee_content_disposition_matches_route_shape() -> None:
    """Mirrors documents/batch content routes: inline + Unicode original name."""
    header = build_content_disposition("ינואר 2020.pdf", disposition="inline")
    response = Response(
        content=b"%PDF-1.4",
        media_type="application/pdf",
        headers={"Content-Disposition": header},
    )
    encoded = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in response.headers.items()]
    assert encoded
    assert response.status_code == 200
