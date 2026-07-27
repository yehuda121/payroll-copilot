"""Temporal legal rule version catalog — overlay on approved YAML (SoT remains YAML files)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml


@dataclass(slots=True)
class LegalRuleVersion:
    rule_id: str
    version: int
    valid_from: str  # ISO date
    valid_to: str | None  # ISO date or None = open
    status: str  # ACTIVE | SUPERSEDED | DRAFT
    scope: str
    content_hash: str
    source_file: str
    snapshot_path: str | None
    created_at: str
    approved_at: str | None
    approved_by: str | None
    source_references: list[dict[str, str]]


class LegalRuleVersionCatalog:
    """Per-rule temporal versions. Never overwrites history; YAML current files stay authoritative for validation."""

    def __init__(self, rules_root: Path | str) -> None:
        self._rules_root = Path(rules_root)
        self._catalog_path = self._rules_root / ".versions" / "rule_temporal_catalog.json"
        self._snapshots_root = self._rules_root / ".versions" / "rule_snapshots"
        self._snapshots_root.mkdir(parents=True, exist_ok=True)
        self._catalog_path.parent.mkdir(parents=True, exist_ok=True)

    def ensure_seeded_from_yaml(self) -> list[LegalRuleVersion]:
        """Seed ACTIVE versions from current YAML if catalog is empty. Idempotent."""
        catalog = self._load()
        if catalog.get("versions"):
            return [LegalRuleVersion(**v) for v in catalog["versions"]]

        seeded: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()
        for yaml_file in sorted(self._rules_root.glob("*.yaml")):
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            file_from = str(data.get("effective_from") or "1970-01-01")[:10]
            for _key, rule_data in (data.get("rules") or {}).items():
                rule_id = str(rule_data.get("id") or "")
                if not rule_id:
                    continue
                content = yaml.safe_dump(rule_data, allow_unicode=True, sort_keys=True)
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                snap_name = f"{rule_id.replace('.', '_')}__v1.yaml"
                snap_path = self._snapshots_root / snap_name
                snap_path.write_text(content, encoding="utf-8")
                seeded.append(
                    asdict(
                        LegalRuleVersion(
                            rule_id=rule_id,
                            version=1,
                            valid_from=file_from,
                            valid_to=None,
                            status="ACTIVE",
                            scope=str(rule_data.get("scope") or "general"),
                            content_hash=content_hash,
                            source_file=yaml_file.name,
                            snapshot_path=str(snap_path.relative_to(self._rules_root)),
                            created_at=now,
                            approved_at=now,
                            approved_by="system_seed",
                            source_references=[
                                {
                                    "title": str(
                                        (rule_data.get("legal_reference") or {}).get("en")
                                        or (rule_data.get("legal_reference") or {}).get("he")
                                        or ""
                                    )
                                }
                            ],
                        )
                    )
                )
        catalog = {"catalog_version": "1", "versions": seeded}
        self._save(catalog)
        return [LegalRuleVersion(**v) for v in seeded]

    def list_versions(self, rule_id: str | None = None) -> list[LegalRuleVersion]:
        self.ensure_seeded_from_yaml()
        versions = [LegalRuleVersion(**v) for v in self._load().get("versions", [])]
        if rule_id:
            versions = [v for v in versions if v.rule_id == rule_id]
        return sorted(versions, key=lambda v: (v.rule_id, v.version))

    def get_active(self, rule_id: str) -> LegalRuleVersion | None:
        actives = [
            v
            for v in self.list_versions(rule_id)
            if v.status == "ACTIVE" and v.valid_to is None
        ]
        if not actives:
            actives = [v for v in self.list_versions(rule_id) if v.status == "ACTIVE"]
        return actives[-1] if actives else None

    def select_as_of(self, rule_id: str, as_of: date) -> LegalRuleVersion | None:
        eligible: list[LegalRuleVersion] = []
        for version in self.list_versions(rule_id):
            if version.status not in {"ACTIVE", "SUPERSEDED"}:
                continue
            vf = date.fromisoformat(version.valid_from)
            vt = date.fromisoformat(version.valid_to) if version.valid_to else None
            if vf <= as_of and (vt is None or vt >= as_of):
                eligible.append(version)
        if not eligible:
            return None
        return max(eligible, key=lambda v: v.version)

    def create_new_version(
        self,
        *,
        rule_id: str,
        rule_body: dict[str, Any],
        effective_date: date,
        approved_by: str,
        source_file: str | None = None,
        scope: str = "general",
        source_references: list[dict[str, str]] | None = None,
    ) -> LegalRuleVersion:
        """Create immutable new ACTIVE version and close previous ACTIVE with valid_to = day_before."""
        existing = self.list_versions(rule_id)
        # Prevent overlapping ACTIVE opens.
        open_actives = [v for v in existing if v.status == "ACTIVE" and v.valid_to is None]
        for active in open_actives:
            prev_from = date.fromisoformat(active.valid_from)
            if effective_date <= prev_from:
                raise ValueError(
                    f"effective_date {effective_date.isoformat()} must be after "
                    f"current version valid_from {active.valid_from}"
                )

        content = yaml.safe_dump(rule_body, allow_unicode=True, sort_keys=True)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        next_version = (max((v.version for v in existing), default=0) + 1)
        close_to = (effective_date - timedelta(days=1)).isoformat()

        catalog = self._load()
        updated: list[dict[str, Any]] = []
        for raw in catalog.get("versions", []):
            if raw.get("rule_id") == rule_id and raw.get("status") == "ACTIVE" and raw.get("valid_to") is None:
                raw = {**raw, "valid_to": close_to, "status": "SUPERSEDED"}
            updated.append(raw)

        now = datetime.now(timezone.utc).isoformat()
        snap_name = f"{rule_id.replace('.', '_')}__v{next_version}_{uuid4().hex[:8]}.yaml"
        snap_path = self._snapshots_root / snap_name
        snap_path.write_text(content, encoding="utf-8")

        new_rec = LegalRuleVersion(
            rule_id=rule_id,
            version=next_version,
            valid_from=effective_date.isoformat(),
            valid_to=None,
            status="ACTIVE",
            scope=scope,
            content_hash=content_hash,
            source_file=source_file or (open_actives[0].source_file if open_actives else "unknown.yaml"),
            snapshot_path=str(snap_path.relative_to(self._rules_root)),
            created_at=now,
            approved_at=now,
            approved_by=approved_by,
            source_references=source_references or [],
        )
        updated.append(asdict(new_rec))
        catalog["versions"] = updated
        self._save(catalog)
        return new_rec

    def detect_active_overlap(self, rule_id: str) -> list[tuple[LegalRuleVersion, LegalRuleVersion]]:
        """Return pairs of overlapping ACTIVE/SUPERSEDED intervals (should be empty)."""
        versions = [
            v
            for v in self.list_versions(rule_id)
            if v.status in {"ACTIVE", "SUPERSEDED"}
        ]
        overlaps: list[tuple[LegalRuleVersion, LegalRuleVersion]] = []
        for i, a in enumerate(versions):
            a_from = date.fromisoformat(a.valid_from)
            a_to = date.fromisoformat(a.valid_to) if a.valid_to else date.max
            for b in versions[i + 1 :]:
                b_from = date.fromisoformat(b.valid_from)
                b_to = date.fromisoformat(b.valid_to) if b.valid_to else date.max
                if a_from <= b_to and b_from <= a_to:
                    overlaps.append((a, b))
        return overlaps

    def _load(self) -> dict[str, Any]:
        if not self._catalog_path.exists():
            return {"catalog_version": "1", "versions": []}
        return json.loads(self._catalog_path.read_text(encoding="utf-8"))

    def _save(self, catalog: dict[str, Any]) -> None:
        self._catalog_path.write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
