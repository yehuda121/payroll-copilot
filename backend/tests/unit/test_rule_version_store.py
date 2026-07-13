"""Tests for rule version store used by accountant rule editing."""

from pathlib import Path

from payroll_copilot.application.services.rule_version_store import RuleVersionStore


def test_rule_version_write_and_rollback(tmp_path: Path) -> None:
    rules_dir = tmp_path / "labor_law"
    rules_dir.mkdir()
    target = rules_dir / "sample.yaml"
    target.write_text("version: '1'\nrules: []\n", encoding="utf-8")

    store = RuleVersionStore(str(rules_dir))
    first = store.write_with_version(
        filename="sample.yaml",
        content="version: '2'\nrules: []\n",
        reason="Raise version for test",
        actor_user_id=None,
    )
    assert "version: '2'" in store.read_current("sample.yaml")
    versions = store.list_versions("sample.yaml")
    assert len(versions) == 1
    assert versions[0].version_id == first.version_id

    # first.version_id archives the pre-edit content ('1')
    store.rollback(
        filename="sample.yaml",
        version_id=first.version_id,
        reason="Rollback test",
        actor_user_id=None,
    )
    restored = store.read_current("sample.yaml")
    assert "version: '1'" in restored
