"""Deterministic payroll-accountant legal update check.

Normal payslip validation NEVER uses this module (no MCP / network).

Accountant explicitly clicks "Check legal updates" → compare local YAML
against normalized external candidates → optional immutable new versions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from payroll_copilot.application.services.legal_rule_version_catalog import (
    LegalRuleVersion,
    LegalRuleVersionCatalog,
)
from payroll_copilot.application.services.rule_version_store import RuleVersionStore
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader


@dataclass(slots=True)
class ExternalLegalCandidate:
    """Normalized external legal-rule change proposed for comparison."""

    rule_id: str
    parameter_key: str
    proposed_value: Any
    legal_source: str
    effective_date: date | None = None  # None → treat as today when classifying
    explanation: str = ""
    rule_name: str | None = None


@dataclass(slots=True)
class LegalRuleDifference:
    change_id: str
    rule_id: str
    rule_name: str
    parameter_key: str
    current_value: Any
    proposed_value: Any
    legal_source: str
    effective_date: str | None
    explanation: str
    selectable: bool
    kind: str  # "effective" | "future"


@dataclass(slots=True)
class LegalUpdateCheckResult:
    status: str  # "up_to_date" | "differences_found"
    message: str
    local_bundle_version: str
    checked_at: str
    effective_changes: list[LegalRuleDifference] = field(default_factory=list)
    future_changes: list[LegalRuleDifference] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "local_bundle_version": self.local_bundle_version,
            "checked_at": self.checked_at,
            "effective_changes": [asdict(c) for c in self.effective_changes],
            "future_changes": [asdict(c) for c in self.future_changes],
        }


@dataclass(slots=True)
class LegalUpdateApplyResult:
    created_versions: list[LegalRuleVersion] = field(default_factory=list)
    skipped_change_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_versions": [asdict(v) for v in self.created_versions],
            "skipped_change_ids": list(self.skipped_change_ids),
        }


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, date):
        return value.isoformat()
    return json.loads(json.dumps(value, default=str))


def _values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return _json_safe(a) == _json_safe(b)


def classify_effective_date(
    *,
    external_date: date | None,
    today: date,
) -> tuple[date, str]:
    """Return (resolved_date, kind) where kind is effective|future.

    A. past/today → effective with that date
    B. missing → effective with today
    C. future → future (informational only)
    """
    if external_date is None:
        return today, "effective"
    if external_date > today:
        return external_date, "future"
    return external_date, "effective"


def extract_minimum_wage_candidates(
    text: str,
    *,
    legal_source: str,
) -> list[ExternalLegalCandidate]:
    """Deterministic extraction of hourly minimum-wage amounts from source text."""
    candidates: list[ExternalLegalCandidate] = []
    # Match patterns like "32.11" near minimum-wage wording, or explicit "amount: 34.50"
    amount_patterns = [
        re.compile(
            r"(?:minimum\s*wage|שכר\s*מינימום)[^\d]{0,40}(\d{2,3}(?:\.\d{1,2})?)",
            re.IGNORECASE,
        ),
        re.compile(r"amount\s*[:=]\s*(\d{2,3}(?:\.\d{1,2})?)", re.IGNORECASE),
        re.compile(r"official_rate\s*[:=]\s*(\d{2,3}(?:\.\d{1,2})?)", re.IGNORECASE),
    ]
    date_match = re.search(
        r"(?:effective(?:_from|_date)?|בתוקף|תוקף)\s*[:=]?\s*(\d{4}-\d{2}-\d{2})",
        text,
        re.IGNORECASE,
    )
    eff: date | None = None
    if date_match:
        try:
            eff = date.fromisoformat(date_match.group(1))
        except ValueError:
            eff = None

    seen: set[str] = set()
    for pattern in amount_patterns:
        for match in pattern.finditer(text):
            raw = match.group(1)
            if raw in seen:
                continue
            seen.add(raw)
            try:
                amount = float(raw)
            except ValueError:
                continue
            candidates.append(
                ExternalLegalCandidate(
                    rule_id="legal.minimum_wage",
                    parameter_key="amount",
                    proposed_value=amount,
                    legal_source=legal_source,
                    effective_date=eff,
                    explanation=f"Extracted hourly minimum wage {amount} from legal source text.",
                    rule_name="Hourly minimum wage",
                )
            )
    return candidates


class LegalUpdateCheckService:
    """Compare local active legal rules with normalized external candidates."""

    def __init__(
        self,
        *,
        rules_path: str | Path,
        catalog: LegalRuleVersionCatalog | None = None,
        today: date | None = None,
    ) -> None:
        self._rules_path = Path(rules_path)
        self._loader = YamlLegalRulesLoader(self._rules_path)
        self._catalog = catalog or LegalRuleVersionCatalog(self._rules_path)
        self._today = today or date.today()

    def check(
        self,
        *,
        external_candidates: list[ExternalLegalCandidate] | None = None,
        external_text_by_source: dict[str, str] | None = None,
    ) -> LegalUpdateCheckResult:
        """Compare local rules to external candidates.

        Prefer structured ``external_candidates`` (tests / MCP-normalized input).
        Optionally also parse ``external_text_by_source`` deterministically.
        """
        bundle = self._loader.load_merged_rules()
        candidates = list(external_candidates or [])
        for source_id, text in (external_text_by_source or {}).items():
            candidates.extend(
                extract_minimum_wage_candidates(text, legal_source=source_id)
            )

        return self._compare(bundle_version=bundle.version, candidates=candidates)

    async def check_from_configured_sources(self) -> LegalUpdateCheckResult:
        """Accountant-triggered fetch of configured legal sources (not used by validation)."""
        import httpx

        from payroll_copilot.application.services.legal_knowledge_sync import (
            normalize_source_text,
        )
        from payroll_copilot.application.services.legal_source_registry import (
            LegalSourceRegistry,
        )

        texts: dict[str, str] = {}
        registry = LegalSourceRegistry()
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for source in registry.load():
                if not source.enabled or not source.url:
                    continue
                try:
                    response = await client.get(source.url)
                    response.raise_for_status()
                    texts[source.source_id] = normalize_source_text(response.text)
                except Exception:  # noqa: BLE001 — source failures must not crash UI
                    continue
        return self.check(external_text_by_source=texts or None)

    def _compare(
        self,
        *,
        bundle_version: str,
        candidates: list[ExternalLegalCandidate],
    ) -> LegalUpdateCheckResult:
        effective: list[LegalRuleDifference] = []
        future: list[LegalRuleDifference] = []
        checked_at = datetime.now(timezone.utc).isoformat()
        bundle = self._loader.load_merged_rules()

        for cand in candidates:
            local = next(
                (r for r in bundle.rules.values() if r.rule_id == cand.rule_id),
                None,
            )
            if local is None:
                continue
            current = local.parameters.get(cand.parameter_key)
            if _values_equal(current, cand.proposed_value):
                continue

            resolved, kind = classify_effective_date(
                external_date=cand.effective_date, today=self._today
            )
            name = cand.rule_name or (
                local.description.get("en")
                or local.description.get("he")
                or cand.rule_id
            )
            diff = LegalRuleDifference(
                change_id=str(uuid4()),
                rule_id=cand.rule_id,
                rule_name=str(name),
                parameter_key=cand.parameter_key,
                current_value=_json_safe(current),
                proposed_value=_json_safe(cand.proposed_value),
                legal_source=cand.legal_source,
                effective_date=resolved.isoformat(),
                explanation=cand.explanation
                or f"{cand.parameter_key} differs from local active rule.",
                selectable=kind == "effective",
                kind=kind,
            )
            if kind == "future":
                future.append(diff)
            else:
                effective.append(diff)

        if not effective and not future:
            return LegalUpdateCheckResult(
                status="up_to_date",
                message="Legal rules are up to date.",
                local_bundle_version=bundle_version,
                checked_at=checked_at,
            )
        return LegalUpdateCheckResult(
            status="differences_found",
            message="Legal rule differences require review.",
            local_bundle_version=bundle_version,
            checked_at=checked_at,
            effective_changes=effective,
            future_changes=future,
        )

    def apply_selected(
        self,
        *,
        changes: list[LegalRuleDifference],
        selected_change_ids: list[str],
        approved_by: str,
    ) -> LegalUpdateApplyResult:
        """Create immutable versions for selected *effective* changes only.

        Groups by effective_date so mixed dates never collapse into one version date.
        Zero selections → no versions (same as Cancel).
        """
        selected = {
            c.change_id
            for c in changes
            if c.change_id in set(selected_change_ids)
            and c.selectable
            and c.kind == "effective"
        }
        if not selected:
            return LegalUpdateApplyResult()

        by_date: dict[str, list[LegalRuleDifference]] = {}
        skipped: list[str] = []
        for change in changes:
            if change.change_id not in selected:
                if change.change_id in set(selected_change_ids):
                    skipped.append(change.change_id)
                continue
            key = change.effective_date or self._today.isoformat()
            by_date.setdefault(key, []).append(change)

        created: list[LegalRuleVersion] = []
        self._catalog.ensure_seeded_from_yaml()
        store = RuleVersionStore(self._rules_path)

        for eff_str in sorted(by_date.keys()):
            eff = date.fromisoformat(eff_str)
            for change in by_date[eff_str]:
                rule_body, source_file = self._build_updated_rule_body(change)
                version = self._catalog.create_new_version(
                    rule_id=change.rule_id,
                    rule_body=rule_body,
                    effective_date=eff,
                    approved_by=approved_by,
                    source_file=source_file,
                    source_references=[
                        {
                            "title": change.legal_source,
                            "change_id": change.change_id,
                        }
                    ],
                )
                self._write_yaml_parameter(change, store=store, approved_by=approved_by)
                created.append(version)

        return LegalUpdateApplyResult(created_versions=created, skipped_change_ids=skipped)

    def _build_updated_rule_body(
        self, change: LegalRuleDifference
    ) -> tuple[dict[str, Any], str | None]:
        loader = self._loader
        bundle = loader.load_merged_rules()
        local = next(r for r in bundle.rules.values() if r.rule_id == change.rule_id)
        params = dict(local.parameters)
        params[change.parameter_key] = change.proposed_value
        schedule = list(params.get("schedule") or [])
        if change.effective_date and change.parameter_key == "amount":
            schedule = [
                row
                for row in schedule
                if str(row.get("effective_from") or "") != change.effective_date
            ]
            schedule.append(
                {
                    "effective_from": change.effective_date,
                    change.parameter_key: change.proposed_value,
                }
            )
            params["schedule"] = schedule
        body = {
            "id": local.rule_id,
            "description": local.description,
            "parameters": params,
            "legal_reference": local.legal_reference,
            "severity": (
                local.severity.value
                if hasattr(local.severity, "value")
                else str(local.severity)
            ),
        }
        source_file = None
        for name, file_bundle in loader.load_all().items():
            if any(r.rule_id == change.rule_id for r in file_bundle.rules.values()):
                source_file = f"{name}.yaml"
                break
        return body, source_file

    def _write_yaml_parameter(
        self,
        change: LegalRuleDifference,
        *,
        store: RuleVersionStore,
        approved_by: str,
    ) -> None:
        _, source_file = self._build_updated_rule_body(change)
        if not source_file:
            return
        current = yaml.safe_load(store.read_current(source_file)) or {}
        rules = current.get("rules") or {}
        replaced = False
        for key, data in list(rules.items()):
            if str(data.get("id")) != change.rule_id:
                continue
            params = dict(data.get("parameters") or {})
            params[change.parameter_key] = change.proposed_value
            if change.effective_date and change.parameter_key == "amount":
                schedule = [
                    row
                    for row in list(params.get("schedule") or [])
                    if str(row.get("effective_from") or "") != change.effective_date
                ]
                schedule.append(
                    {
                        "effective_from": change.effective_date,
                        change.parameter_key: change.proposed_value,
                    }
                )
                params["schedule"] = schedule
            data = {**data, "parameters": params}
            rules[key] = data
            replaced = True
            break
        if not replaced:
            return
        current["rules"] = rules
        from uuid import UUID

        try:
            actor = UUID(approved_by)
        except ValueError:
            actor = uuid4()
        store.write_with_version(
            filename=source_file,
            content=yaml.safe_dump(current, allow_unicode=True, sort_keys=False),
            reason=f"Legal update check applied: {change.rule_id}.{change.parameter_key}",
            actor_user_id=actor,
        )


def content_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
