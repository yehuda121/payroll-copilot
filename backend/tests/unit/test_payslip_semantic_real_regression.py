"""Harness for real payslip semantic regression — skipped until fixtures exist."""

from __future__ import annotations

from pathlib import Path

import pytest

_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "documents"
    / "payslips"
    / "real_regression"
)
_DOCUMENTS = _FIXTURE_ROOT / "documents"
_MANIFESTS = _FIXTURE_ROOT / "manifests"


def _manifest_paths() -> list[Path]:
    if not _MANIFESTS.is_dir():
        return []
    return sorted(_MANIFESTS.glob("*.json"))


@pytest.mark.skipif(
    not any((_DOCUMENTS / p.stem).with_suffix(suf).exists() for p in _manifest_paths() for suf in (".pdf", ".png", ".jpg")),
    reason="Real payslip regression documents are not present in the repository",
)
@pytest.mark.parametrize("manifest_path", _manifest_paths() or [None])
def test_real_payslip_semantic_regression_placeholder(manifest_path: Path | None) -> None:
    """When documents + manifests are added, run semantic_v1 and assert expected keys."""
    if manifest_path is None:
        pytest.skip("No manifests")
    # Intentionally minimal until approved anonymized fixtures are added.
    assert manifest_path.is_file()
