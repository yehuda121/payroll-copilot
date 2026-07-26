"""YAML legal rules loader with caching."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from payroll_copilot.application.ports import LegalRulesLoader
from payroll_copilot.domain.enums import FindingSeverity
from payroll_copilot.domain.rules import LegalRuleConfig, LegalRulesBundle


class YamlLegalRulesLoader(LegalRulesLoader):
    """Loads Israeli labor law rules from YAML files."""

    def __init__(self, rules_path: str | Path) -> None:
        self._path = Path(rules_path)
        self._cache: dict[str, Any] = {}
        self._hashes: dict[str, str] = {}

    def load_all(self) -> dict[str, LegalRulesBundle]:
        bundles: dict[str, LegalRulesBundle] = {}
        if not self._path.exists():
            return bundles

        for yaml_file in sorted(self._path.glob("*.yaml")):
            bundle = self._load_file(yaml_file)
            bundles[yaml_file.stem] = bundle
        return bundles

    def load_merged_rules(self) -> LegalRulesBundle:
        """Merge all YAML files into a single rules bundle for validation."""
        return self.load_merged_rules_as_of(None)

    def load_merged_rules_as_of(self, as_of: date | None) -> LegalRulesBundle:
        """Merge YAML rules; as_of reserved for future multi-file version trees.

        Parameter-level schedules are resolved inside individual rules via
        resolve_parameters_as_of. Bundle.effective_from is the max file stamp
        that is <= as_of when as_of is provided; otherwise last-file-wins.
        """
        all_rules: dict[str, LegalRuleConfig] = {}
        version = "0.0.0"
        effective_from = "1970-01-01"
        best_stamp: date | None = None

        for yaml_file in sorted(self._path.glob("*.yaml")):
            data = self._read_yaml(yaml_file)
            file_from = data.get("effective_from", "1970-01-01")
            file_date = None
            try:
                file_date = date.fromisoformat(str(file_from)[:10])
            except ValueError:
                file_date = None
            if as_of is not None and file_date is not None and file_date > as_of:
                continue
            version = data.get("version", version)
            effective_from = data.get("effective_from", effective_from)
            if file_date is not None:
                best_stamp = file_date if best_stamp is None else max(best_stamp, file_date)
            for rule_key, rule_data in data.get("rules", {}).items():
                all_rules[rule_key] = self._parse_rule(rule_key, rule_data)

        return LegalRulesBundle(
            version=version,
            effective_from=effective_from,
            rules=all_rules,
        )

    def get_file_hash(self, filename: str) -> str:
        filepath = self._path / filename
        if not filepath.exists():
            return ""
        content = filepath.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def reload(self) -> None:
        self._cache.clear()
        self._hashes.clear()

    def _load_file(self, filepath: Path) -> LegalRulesBundle:
        data = self._read_yaml(filepath)
        rules = {
            key: self._parse_rule(key, val)
            for key, val in data.get("rules", {}).items()
        }
        return LegalRulesBundle(
            version=data.get("version", "0.0.0"),
            effective_from=data.get("effective_from", "1970-01-01"),
            rules=rules,
        )

    def _read_yaml(self, filepath: Path) -> dict[str, Any]:
        stem = filepath.stem
        content = filepath.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        if stem in self._cache and self._hashes.get(stem) == file_hash:
            return self._cache[stem]

        data = yaml.safe_load(content.decode("utf-8")) or {}
        self._cache[stem] = data
        self._hashes[stem] = file_hash
        return data

    @staticmethod
    def _parse_rule(rule_key: str, rule_data: dict[str, Any]) -> LegalRuleConfig:
        severity_str = rule_data.get("severity", "warning")
        rule_id = rule_data.get("id", f"legal.{rule_key}")
        return LegalRuleConfig(
            rule_id=rule_id,
            description=rule_data.get("description", {}),
            parameters=rule_data.get("parameters", {}),
            legal_reference=rule_data.get("legal_reference", {}),
            severity=FindingSeverity(severity_str),
        )
