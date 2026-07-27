"""Legal source registry — only verified/configured URLs; never invent sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from payroll_copilot.application.dto.legal_knowledge import (
    AuthorityLevel,
    LegalSourceRecord,
    SourceType,
)
from payroll_copilot.infrastructure.config.settings import get_settings


class LegalSourceRegistry:
    """Loads maintainable watched/discovery source definitions from config."""

    def __init__(self, registry_path: str | Path | None = None) -> None:
        settings = get_settings()
        if registry_path is None:
            root = Path(__file__).resolve().parents[4]
            registry_path = root / "config" / "legal_sources" / "registry.json"
        self._path = Path(registry_path)
        self._kol_zchut_base = (settings.kol_zchut_base_url or "").rstrip("/")

    def load(self) -> list[LegalSourceRecord]:
        raw = self._read()
        sources: list[LegalSourceRecord] = []
        for item in raw.get("sources", []):
            url = item.get("url")
            # Only allow the configured Kol Zchut base from settings when provider matches.
            if item.get("provider") == "kol_zchut" and self._kol_zchut_base:
                url = self._kol_zchut_base
            coverage = "configured" if url else "unconfigured"
            if item.get("enabled") is False and not url:
                coverage = "unconfigured"
            sources.append(
                LegalSourceRecord(
                    source_id=item["source_id"],
                    provider=item.get("provider", "unknown"),
                    source_type=SourceType(item["source_type"]),
                    url=url,
                    authority_level=AuthorityLevel(item.get("authority_level", "SECONDARY_INTERPRETATION")),
                    related_rule_ids=list(item.get("related_rule_ids") or []),
                    enabled=bool(item.get("enabled", False)) and bool(url),
                    notes=item.get("notes") or "",
                    coverage_status=coverage,
                )
            )
        return sources

    def get(self, source_id: str) -> LegalSourceRecord | None:
        for source in self.load():
            if source.source_id == source_id:
                return source
        return None

    def rule_coverage_map(self) -> dict[str, dict[str, Any]]:
        """Map internal rule_id → watched/discovery/official coverage status."""
        mapping: dict[str, dict[str, Any]] = {}
        for source in self.load():
            for rule_id in source.related_rule_ids:
                entry = mapping.setdefault(
                    rule_id,
                    {
                        "rule_id": rule_id,
                        "watched_sources": [],
                        "discovery_sources": [],
                        "official_source": None,
                        "coverage_status": "unconfigured",
                    },
                )
                if source.source_type == SourceType.WATCHED_SOURCE:
                    entry["watched_sources"].append(source.source_id)
                    if source.authority_level == AuthorityLevel.OFFICIAL and source.url:
                        entry["official_source"] = source.source_id
                else:
                    entry["discovery_sources"].append(source.source_id)
                if source.url and source.enabled:
                    entry["coverage_status"] = "configured"
        return mapping

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"registry_version": "missing", "sources": []}
        return json.loads(self._path.read_text(encoding="utf-8"))
