"""Field catalogs for primary_company summary and deduction rows."""

from __future__ import annotations

SUMMARY_FIELD_NAMES: tuple[str, ...] = (
    'סה"כ תשלומים',
    "ניכויי חובה וגמל",
    "שכר נטו",
    "נטו לתשלום",
)

INCOME_TAX = "מס הכנסה"
INCOME_TAX_MARGINAL = "מס הכנסה שולי"
NATIONAL_INSURANCE = "ביטוח לאומי"
HEALTH_TAX = "מס בריאות"

DEDUCTION_FIELD_NAMES: tuple[str, ...] = (
    INCOME_TAX,
    INCOME_TAX_MARGINAL,
    NATIONAL_INSURANCE,
    HEALTH_TAX,
)

# Label as printed on the row → (amount field, rate field)
DEDUCTION_ROW_LABELS: dict[str, tuple[str, str | None]] = {
    INCOME_TAX_MARGINAL: (INCOME_TAX, INCOME_TAX_MARGINAL),
    INCOME_TAX: (INCOME_TAX, None),
    NATIONAL_INSURANCE: (NATIONAL_INSURANCE, None),
    HEALTH_TAX: (HEALTH_TAX, None),
}

EMPLOYMENT_SCOPE_LABEL = "היקף משרה"
