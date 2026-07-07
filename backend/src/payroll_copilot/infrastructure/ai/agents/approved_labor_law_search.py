"""Approved local legal rule search — YAML-backed until vector RAG is ready."""

from __future__ import annotations

from payroll_copilot.application.ports.assistant import ApprovedLaborLawSearchPort, LaborLawSearchHit
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader


class YamlApprovedLaborLawSearch(ApprovedLaborLawSearchPort):
    """Keyword search over approved local YAML legal rules."""

    def __init__(self, rules_path: str) -> None:
        self._loader = YamlLegalRulesLoader(rules_path)

    def search(self, query: str, *, locale: str = "en", limit: int = 5) -> list[LaborLawSearchHit]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        tokens = [token for token in normalized_query.split() if len(token) > 2]
        hits: list[tuple[int, LaborLawSearchHit]] = []

        for filename, bundle in self._loader.load_all().items():
            for rule_key, rule in bundle.rules.items():
                searchable_parts = [
                    rule_key.lower(),
                    rule.rule_id.lower(),
                    *rule.description.values(),
                    *rule.legal_reference.values(),
                    str(rule.parameters),
                ]
                searchable = " ".join(searchable_parts).lower()
                score = sum(1 for token in tokens if token in searchable)
                if score == 0:
                    continue

                title = rule.description.get(locale) or rule.description.get("en") or rule_key
                legal_reference = rule.legal_reference.get(locale) or rule.legal_reference.get("en")
                summary = (
                    f"Approved local rule '{rule_key}' from {filename}.yaml. "
                    f"Parameters: {rule.parameters}"
                )
                hits.append(
                    (
                        score,
                        LaborLawSearchHit(
                            rule_key=rule_key,
                            title=title,
                            summary=summary,
                            legal_reference=legal_reference,
                            source_file=f"{filename}.yaml",
                        ),
                    )
                )

        hits.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in hits[:limit]]
