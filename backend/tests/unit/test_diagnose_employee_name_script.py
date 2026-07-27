"""Read-only employee_name diagnostic tool does not alter extraction payloads."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "dev"
    / "diagnose_employee_name_extraction.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("diagnose_employee_name_extraction", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_diagnose_reports_missing_outcome_without_mutating_payload() -> None:
    mod = _load()
    payload = {
        "raw_text": "סבירסקי אורית\nת.ז.: 304913619",
        "ocr_result": {"pages": [{"page": 1, "lines": [{"text": "סבירסקי אורית"}]}]},
        "structured_data": {
            "extractor_meta": {"employee_name_outcome": "employee_name_missing"},
            "dynamic_entries": [],
            "employee_name": {"value": None, "status": "MISSING"},
        },
        "warnings": [],
    }
    before = str(payload)
    result = mod.diagnose(payload)
    assert str(payload) == before
    assert result["employee_name_outcome"] == "employee_name_missing"
    assert result["stages"]
    assert any("never reads employee profile" in n.lower() for n in result["notes"])


def test_diagnose_detects_grounded_entry() -> None:
    mod = _load()
    result = mod.diagnose(
        {
            "raw_text": "name line",
            "ocr_result": {},
            "structured_data": {
                "extractor_meta": {"employee_name_outcome": "employee_name_grounded"},
                "dynamic_entries": [
                    {"key": "employee_name", "value": "Dana Levi", "status": "FOUND"}
                ],
                "employee_name": {"value": "Dana Levi", "status": "FOUND"},
            },
        }
    )
    assert result["first_broken_stage_estimate"] == "none_detected_or_name_present"
