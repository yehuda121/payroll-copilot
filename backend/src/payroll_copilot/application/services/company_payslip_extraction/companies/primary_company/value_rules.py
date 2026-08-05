"""Field-scoped value rules for the primary_company payslip format."""

from __future__ import annotations

YES_NO_VALUE_ALIASES: dict[str, str] = {
    "אל": "לא",
    "ןכ": "כן",
    "לא": "לא",
    "כן": "כן",
}

EMPLOYMENT_TYPE_TOKENS: dict[str, str] = {
    "הרשמ": "משרה",
    "משרה": "משרה",
    "תישדוח": "חודשית",
    "חודשית": "חודשית",
    "ישדוח": "חודשי",
    "חודשי": "חודשי",
    "יפל": "לפי",
    "לפי": "לפי",
    "םימי": "ימים",
    "ימים": "ימים",
    "תועש": "שעות",
    "שעות": "שעות",
    "העש": "שעה",
    "שעה": "שעה",
    "םוי": "יום",
    "יום": "יום",
}
