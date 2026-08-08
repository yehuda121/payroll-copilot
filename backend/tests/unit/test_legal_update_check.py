"""Focused tests for accountant legal update check (deterministic, no auto-apply)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from payroll_copilot.application.services.legal_update_check import (
    ExternalLegalCandidate,
    LegalRuleDifference,
    LegalUpdateCheckService,
    classify_effective_date,
)


@pytest.fixture
def rules_tmp(tmp_path: Path) -> Path:
    src = Path("config/rules/labor_law")
    dest = tmp_path / "labor_law"
    shutil.copytree(src, dest)
    # Avoid copying mutable version catalog from workspace.
    versions = dest / ".versions"
    if versions.exists():
        shutil.rmtree(versions)
    return dest


def test_classify_effective_date_rules() -> None:
    today = date(2026, 7, 24)
    assert classify_effective_date(external_date=date(2026, 1, 1), today=today) == (
        date(2026, 1, 1),
        "effective",
    )
    assert classify_effective_date(external_date=today, today=today) == (today, "effective")
    assert classify_effective_date(external_date=None, today=today) == (today, "effective")
    assert classify_effective_date(external_date=date(2027, 1, 1), today=today) == (
        date(2027, 1, 1),
        "future",
    )


def test_no_differences_creates_no_version(rules_tmp: Path) -> None:
    service = LegalUpdateCheckService(rules_path=rules_tmp, today=date(2026, 7, 24))
    result = service.check(
        external_candidates=[
            ExternalLegalCandidate(
                rule_id="legal.minimum_wage",
                parameter_key="amount",
                proposed_value=32.11,
                legal_source="test",
                effective_date=date(2026, 7, 1),
            )
        ]
    )
    assert result.status == "up_to_date"
    assert result.message == "Legal rules are up to date."
    assert result.effective_changes == []
    applied = service.apply_selected(
        changes=[],
        selected_change_ids=[],
        approved_by="00000000-0000-0000-0000-000000000001",
    )
    assert applied.created_versions == []


def test_past_and_today_selectable_future_informational(rules_tmp: Path) -> None:
    today = date(2026, 7, 24)
    service = LegalUpdateCheckService(rules_path=rules_tmp, today=today)
    result = service.check(
        external_candidates=[
            ExternalLegalCandidate(
                rule_id="legal.minimum_wage",
                parameter_key="amount",
                proposed_value=33.0,
                legal_source="kol-zchut",
                effective_date=date(2026, 4, 1),
                explanation="Past increase",
            ),
            ExternalLegalCandidate(
                rule_id="legal.minimum_wage",
                parameter_key="amount",
                proposed_value=34.0,
                legal_source="kol-zchut",
                effective_date=date(2027, 1, 1),
                explanation="Future increase",
            ),
        ]
    )
    assert result.status == "differences_found"
    assert len(result.effective_changes) == 1
    assert result.effective_changes[0].selectable is True
    assert result.effective_changes[0].proposed_value == 33.0
    assert len(result.future_changes) == 1
    assert result.future_changes[0].selectable is False
    assert result.future_changes[0].proposed_value == 34.0


def test_missing_effective_date_uses_today(rules_tmp: Path) -> None:
    today = date(2026, 7, 24)
    service = LegalUpdateCheckService(rules_path=rules_tmp, today=today)
    result = service.check(
        external_candidates=[
            ExternalLegalCandidate(
                rule_id="legal.minimum_wage",
                parameter_key="amount",
                proposed_value=33.5,
                legal_source="gov",
                effective_date=None,
            )
        ]
    )
    assert result.effective_changes[0].effective_date == today.isoformat()
    assert result.effective_changes[0].selectable is True


def test_cancel_and_zero_selection_create_nothing(rules_tmp: Path) -> None:
    today = date(2026, 7, 24)
    service = LegalUpdateCheckService(rules_path=rules_tmp, today=today)
    result = service.check(
        external_candidates=[
            ExternalLegalCandidate(
                rule_id="legal.minimum_wage",
                parameter_key="amount",
                proposed_value=35.0,
                legal_source="gov",
                effective_date=date(2026, 6, 1),
            )
        ]
    )
    change = result.effective_changes[0]
    # Cancel / empty selection
    applied = service.apply_selected(
        changes=result.effective_changes + result.future_changes,
        selected_change_ids=[],
        approved_by="00000000-0000-0000-0000-000000000001",
    )
    assert applied.created_versions == []
    # Explicitly selecting a future change must not apply
    future = LegalRuleDifference(
        change_id="future-1",
        rule_id=change.rule_id,
        rule_name=change.rule_name,
        parameter_key=change.parameter_key,
        current_value=change.current_value,
        proposed_value=99.0,
        legal_source="gov",
        effective_date="2027-01-01",
        explanation="future",
        selectable=False,
        kind="future",
    )
    applied2 = service.apply_selected(
        changes=[future],
        selected_change_ids=["future-1"],
        approved_by="00000000-0000-0000-0000-000000000001",
    )
    assert applied2.created_versions == []


def test_confirm_creates_immutable_version_and_uncheck_excludes(rules_tmp: Path) -> None:
    today = date(2026, 7, 24)
    service = LegalUpdateCheckService(rules_path=rules_tmp, today=today)
    result = service.check(
        external_candidates=[
            ExternalLegalCandidate(
                rule_id="legal.minimum_wage",
                parameter_key="amount",
                proposed_value=36.0,
                legal_source="gov",
                effective_date=date(2026, 5, 1),
                explanation="selected",
            ),
            ExternalLegalCandidate(
                rule_id="legal.youth.minimum_age",
                parameter_key="min_age",
                proposed_value=16,
                legal_source="gov",
                effective_date=date(2026, 5, 1),
                explanation="unchecked",
            ),
        ]
    )
    assert len(result.effective_changes) == 2
    keep = result.effective_changes[0]
    drop = result.effective_changes[1]

    before_catalog = service._catalog.list_versions("legal.minimum_wage")
    before_count = len(before_catalog)

    applied = service.apply_selected(
        changes=result.effective_changes,
        selected_change_ids=[keep.change_id],  # drop unchecked
        approved_by="00000000-0000-0000-0000-000000000001",
    )
    assert len(applied.created_versions) == 1
    assert applied.created_versions[0].rule_id == keep.rule_id
    assert applied.created_versions[0].valid_from == "2026-05-01"

    after = service._catalog.list_versions("legal.minimum_wage")
    assert len(after) == before_count + 1
    # Previous ACTIVE closed — immutable history preserved
    superseded = [v for v in after if v.status == "SUPERSEDED"]
    assert superseded

    # Youth rule unchanged
    youth_versions = service._catalog.list_versions("legal.youth.minimum_age")
    assert all(v.version == 1 for v in youth_versions) or drop.change_id not in {
        c.change_id for c in applied.created_versions
    }

    data = yaml.safe_load((rules_tmp / "labor_law.yaml").read_text(encoding="utf-8"))
    amount = data["rules"]["minimum_wage_hourly"]["parameters"]["amount"]
    assert float(amount) == 36.0


def test_mixed_effective_dates_create_separate_versions(rules_tmp: Path) -> None:
    today = date(2026, 7, 24)
    service = LegalUpdateCheckService(rules_path=rules_tmp, today=today)
    # Two different rules, two dates — group by date without collapsing.
    result = service.check(
        external_candidates=[
            ExternalLegalCandidate(
                rule_id="legal.minimum_wage",
                parameter_key="amount",
                proposed_value=37.0,
                legal_source="gov",
                effective_date=date(2026, 3, 1),
            ),
            ExternalLegalCandidate(
                rule_id="legal.youth.minimum_age",
                parameter_key="min_age",
                proposed_value=16,
                legal_source="gov",
                effective_date=date(2026, 4, 1),
            ),
        ]
    )
    applied = service.apply_selected(
        changes=result.effective_changes,
        selected_change_ids=[c.change_id for c in result.effective_changes],
        approved_by="00000000-0000-0000-0000-000000000001",
    )
    dates = {v.valid_from for v in applied.created_versions}
    assert dates == {"2026-03-01", "2026-04-01"}
