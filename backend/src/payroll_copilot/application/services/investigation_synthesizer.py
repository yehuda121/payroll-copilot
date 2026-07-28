"""Deterministic synthesizer for payroll investigation answers.

Produces natural, locale-matched prose from deterministic deltas only —
never recalculates tax or salary rules.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from payroll_copilot.application.services.payslip_period_lookback import previous_month
from payroll_copilot.domain.investigation.types import (
    InvestigationFocus,
    InvestigationOutcome,
    LineItemDelta,
    PeriodRef,
)

_HEBREW_LETTER = re.compile(r"[\u0590-\u05FF]")
_ARABIC_LETTER = re.compile(r"[\u0600-\u06FF]")

_FIELD_LABELS_HE: dict[str, str] = {
    "base_salary": "שכר היסוד",
    "gross_salary": "הברוטו",
    "net_salary": "הנטו",
    "amount_paid": "הסכום לתשלום",
    "overtime_hours": "שעות נוספות",
    "regular_hours": "שעות רגילות",
    "travel_expenses": "החזר הנסיעות",
    "income_tax": "מס ההכנסה",
    "national_insurance": "הביטוח הלאומי",
    "health_tax": "מס הבריאות",
    "pension_employee": "ניכוי הפנסיה (חלק עובד)",
    "pension_employer": "הפרשת הפנסיה (מעסיק)",
    "total_deductions": "סך הניכויים",
    "vacation_balance": "יתרת החופשה",
    "sick_leave_balance": "יתרת המחלה",
}

_FIELD_LABELS_EN: dict[str, str] = {
    "base_salary": "base salary",
    "gross_salary": "gross pay",
    "net_salary": "net pay",
    "amount_paid": "amount paid",
    "overtime_hours": "overtime hours",
    "regular_hours": "regular hours",
    "travel_expenses": "travel expenses",
    "income_tax": "income tax",
    "national_insurance": "national insurance",
    "health_tax": "health tax",
    "pension_employee": "employee pension deduction",
    "pension_employer": "employer pension contribution",
    "total_deductions": "total deductions",
    "vacation_balance": "vacation balance",
    "sick_leave_balance": "sick-leave balance",
}

_MONTHS_HE = {
    1: "ינואר",
    2: "פברואר",
    3: "מרץ",
    4: "אפריל",
    5: "מאי",
    6: "יוני",
    7: "יולי",
    8: "אוגוסט",
    9: "ספטמבר",
    10: "אוקטובר",
    11: "נובמבר",
    12: "דצמבר",
}

_MONTHS_EN = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

_FOCUS_HE = {
    InvestigationFocus.GENERAL: "כללי",
    InvestigationFocus.NET_GROSS: "נטו וברוטו",
    InvestigationFocus.OVERTIME: "שעות נוספות",
    InvestigationFocus.DEDUCTIONS: "ניכויים",
    InvestigationFocus.PENSION: "פנסיה",
    InvestigationFocus.LEAVE: "חופשה ומחלה",
    InvestigationFocus.BASE_SALARY: "שכר יסוד",
}

_MONEY_KEYS = frozenset(
    {
        "base_salary",
        "gross_salary",
        "net_salary",
        "amount_paid",
        "travel_expenses",
        "income_tax",
        "national_insurance",
        "health_tax",
        "pension_employee",
        "pension_employer",
        "total_deductions",
    }
)

_PERCENT_LINKED_TO_GROSS = frozenset(
    {
        "pension_employee",
        "pension_employer",
        "income_tax",
        "national_insurance",
        "health_tax",
        "total_deductions",
    }
)


def resolve_response_locale(*, message: str, locale: str | None) -> str:
    """Prefer the user's message script; fall back to requested locale."""
    text = message or ""
    if _HEBREW_LETTER.search(text):
        return "he"
    if _ARABIC_LETTER.search(text):
        return "ar"
    requested = (locale or "").strip().lower()[:2]
    if requested in {"he", "en", "ar"}:
        return requested
    return "he"


def period_label(period: PeriodRef | None, *, locale: str) -> str:
    if period is None:
        return ""
    lang = (locale or "he").lower()[:2]
    if lang == "en":
        return f"{_MONTHS_EN.get(period.month, period.month)} {period.year}"
    if lang == "ar":
        return period.key
    return f"{_MONTHS_HE.get(period.month, period.month)} {period.year}"


def _label(field_key: str, locale: str) -> str:
    lang = (locale or "he").lower()[:2]
    if lang == "en":
        return _FIELD_LABELS_EN.get(field_key, field_key.replace("_", " "))
    return _FIELD_LABELS_HE.get(field_key, field_key)


def _parse_number(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    cleaned = (
        str(value)
        .strip()
        .replace("₪", "")
        .replace("ILS", "")
        .replace("NIS", "")
        .replace(",", "")
        .replace(" ", "")
    )
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _format_number(value: str | None, *, money: bool) -> str:
    number = _parse_number(value)
    if number is None:
        return str(value).strip() if value not in (None, "") else ""
    quantized = number.quantize(Decimal("0.01")) if "." in format(number, "f") else number
    text = f"{quantized:,.2f}".rstrip("0").rstrip(".")
    if money:
        return f"{text} ₪"
    return text


def _format_value(delta: LineItemDelta, side: str) -> str:
    raw = delta.current_value if side == "current" else delta.prior_value
    if raw in (None, ""):
        return ""
    return _format_number(raw, money=delta.field_key in _MONEY_KEYS)


def _abs_delta_text(delta: LineItemDelta) -> str:
    if not delta.absolute_delta:
        return ""
    return _format_number(
        delta.absolute_delta.lstrip("+-"),
        money=delta.field_key in _MONEY_KEYS,
    )


def clarification_no_history(
    *,
    locale: str,
    target: PeriodRef | None,
    message: str = "",
    expected_prior: PeriodRef | None = None,
) -> str:
    lang = resolve_response_locale(message=message, locale=locale)
    prior = expected_prior
    if prior is None and target is not None:
        prior = previous_month(target)
    prior_label = period_label(prior, locale=lang)
    target_label = period_label(target, locale=lang)

    if lang == "en":
        if prior_label:
            return (
                f"I don't have a payslip for {prior_label} in the system to compare"
                f"{f' with {target_label}' if target_label else ''}. "
                "If you upload that earlier payslip — or share the missing figures — "
                "I can continue from there."
            )
        return (
            "I don't have an earlier payslip available for comparison. "
            "Please upload a prior payslip or share the missing context."
        )
    if lang == "ar":
        if prior_label:
            return (
                f"لا تتوفر في النظام قسيمة راتب لـ {prior_label} للمقارنة"
                f"{f' مع {target_label}' if target_label else ''}. "
                "إذا رفعت تلك القسيمة أو زوّدتني بالأرقام الناقصة، أستطيع المتابعة."
            )
        return "لا تتوفر قسيمة راتب سابقة للمقارنة. يرجى رفع قسيمة سابقة أو تزويدي بالسياق الناقص."

    if prior_label:
        return (
            f"חודש {prior_label} אינו זמין במערכת להשוואה"
            f"{f' מול תלוש {target_label}' if target_label else ''}. "
            "אם תעלו את התלוש של אותו חודש — או תציינו את הסכומים החסרים — אוכל להמשיך משם."
        )
    return (
        "לא נמצא תלוש קודם במערכת להשוואה. "
        "אם תעלו תלוש מוקדם יותר או תציינו את ההקשר החסר, אוכל להמשיך משם."
    )


def clarification_no_current(*, locale: str, message: str = "") -> str:
    lang = resolve_response_locale(message=message, locale=locale)
    if lang == "en":
        return (
            "I could not find a payslip for the requested period. "
            "Please specify a month you have uploaded, or upload that payslip first."
        )
    if lang == "ar":
        return (
            "لم أجد قسيمة راتب للفترة المطلوبة. "
            "يرجى تحديد شهر محمّل أو رفع القسيمة أولاً."
        )
    return (
        "לא מצאתי תלוש לתקופה שביקשתם. "
        "ציינו חודש שכבר הועלה במערכת, או העלו את התלוש קודם."
    )


def clarification_insufficient_evidence(
    *,
    locale: str,
    target: PeriodRef | None,
    missing_keys: tuple[str, ...] = (),
    message: str = "",
) -> str:
    lang = resolve_response_locale(message=message, locale=locale)
    target_label = period_label(target, locale=lang)
    if lang == "en":
        return (
            f"I could not complete the investigation"
            f"{f' for {target_label}' if target_label else ''} because essential "
            "payslip details were missing and re-reading the original document "
            "did not fill the gaps. Please re-upload a clearer payslip or share "
            "the missing values — I will not guess."
        )
    if lang == "ar":
        return (
            f"تعذّر إكمال التحقيق"
            f"{f' لـ {target_label}' if target_label else ''} لأن تفاصيل أساسية ناقصة "
            "وإعادة قراءة المستند الأصلي لم تُكمل النقص. "
            "يرجى إعادة رفع قسيمة أوضح أو تزويدي بالقيم الناقصة — ولن أخمن."
        )
    return (
        f"לא הצלחתי להשלים את הבדיקה"
        f"{f' עבור תלוש {target_label}' if target_label else ''} כי חסרים פרטים מהותיים, "
        "וגם קריאת המסמך המקורי לא השלימה את החסר. "
        "אנא העלו תלוש ברור יותר או ציינו את הערכים החסרים — בלי לנחש."
    )


def _delta_sentence_he(delta: LineItemDelta) -> str | None:
    label = _label(delta.field_key, "he")
    prior = _format_value(delta, "prior")
    current = _format_value(delta, "current")
    abs_text = _abs_delta_text(delta)

    if delta.direction == "increased" and prior and current:
        change = f" (עלייה של {abs_text})" if abs_text else ""
        return f"{label} עלה מ-{prior} ל-{current}{change}"
    if delta.direction == "decreased" and prior and current:
        change = f" (ירידה של {abs_text})" if abs_text else ""
        return f"{label} ירד מ-{prior} ל-{current}{change}"
    if delta.direction == "appeared" and current:
        return f"{label} הופיע החודש בסכום של {current}"
    if delta.direction == "disappeared" and prior:
        return f"{label} שהופיע קודם ({prior}) לא מופיע בתלוש הנוכחי"
    if prior and current:
        return f"{label} השתנה מ-{prior} ל-{current}"
    if current:
        return f"{label} בתלוש הנוכחי הוא {current}"
    if prior:
        return f"{label} בתלוש ההשוואה היה {prior}"
    return None


def _delta_sentence_en(delta: LineItemDelta) -> str | None:
    label = _label(delta.field_key, "en")
    prior = _format_value(delta, "prior")
    current = _format_value(delta, "current")
    abs_text = _abs_delta_text(delta)
    if delta.direction == "increased" and prior and current:
        change = f" (up {abs_text})" if abs_text else ""
        return f"Your {label} rose from {prior} to {current}{change}"
    if delta.direction == "decreased" and prior and current:
        change = f" (down {abs_text})" if abs_text else ""
        return f"Your {label} fell from {prior} to {current}{change}"
    if delta.direction == "appeared" and current:
        return f"Your {label} appeared this period at {current}"
    if delta.direction == "disappeared" and prior:
        return f"Your {label} ({prior}) no longer appears on the current payslip"
    if prior and current:
        return f"Your {label} changed from {prior} to {current}"
    return None


def _pick_delta(deltas: list[LineItemDelta], key: str) -> LineItemDelta | None:
    for delta in deltas:
        if delta.field_key == key and delta.direction != "unchanged":
            return delta
    return None


def _causal_bridge_he(
    *,
    focus: InvestigationFocus,
    deltas: list[LineItemDelta],
) -> str | None:
    """Optional natural link when gross moved and a %–linked deduction moved with it."""
    gross = _pick_delta(deltas, "gross_salary")
    if gross is None or gross.direction not in {"increased", "decreased"}:
        return None
    if focus == InvestigationFocus.PENSION:
        linked = _pick_delta(deltas, "pension_employee") or _pick_delta(
            deltas, "pension_employer"
        )
    elif focus == InvestigationFocus.DEDUCTIONS:
        linked = (
            _pick_delta(deltas, "total_deductions")
            or _pick_delta(deltas, "income_tax")
            or _pick_delta(deltas, "pension_employee")
        )
    elif focus in {InvestigationFocus.NET_GROSS, InvestigationFocus.GENERAL}:
        linked = _pick_delta(deltas, "pension_employee") or _pick_delta(
            deltas, "total_deductions"
        )
    else:
        linked = None
    if linked is None or linked.field_key not in _PERCENT_LINKED_TO_GROSS:
        return None
    if linked.direction not in {"increased", "decreased"}:
        return None
    if linked.direction != gross.direction:
        return None

    gross_sentence = _delta_sentence_he(gross)
    linked_label = _label(linked.field_key, "he")
    if not gross_sentence:
        return None
    if gross.direction == "increased":
        return (
            f"הסיבה לשינוי ב{linked_label} קשורה לכך ש{gross_sentence}, "
            f"ומאחר שרכיב זה מחושב לרוב כאחוז מהברוטו, הסכום גדל בהתאם."
        )
    return (
        f"השינוי ב{linked_label} מתיישב עם כך ש{gross_sentence}, "
        f"ומאחר שרכיב זה מחושב לרוב כאחוז מהברוטו, הסכום קטן בהתאם."
    )


def _ordered_deltas(
    deltas: list[LineItemDelta],
    *,
    focus: InvestigationFocus,
) -> list[LineItemDelta]:
    material = [d for d in deltas if d.direction != "unchanged"]
    priority: tuple[str, ...]
    if focus == InvestigationFocus.NET_GROSS:
        priority = ("net_salary", "gross_salary", "total_deductions", "base_salary")
    elif focus == InvestigationFocus.OVERTIME:
        priority = ("overtime_hours", "gross_salary", "net_salary")
    elif focus == InvestigationFocus.PENSION:
        priority = ("pension_employee", "pension_employer", "gross_salary", "net_salary")
    elif focus == InvestigationFocus.DEDUCTIONS:
        priority = (
            "total_deductions",
            "income_tax",
            "national_insurance",
            "health_tax",
            "gross_salary",
            "net_salary",
        )
    elif focus == InvestigationFocus.BASE_SALARY:
        priority = ("base_salary", "gross_salary", "net_salary")
    elif focus == InvestigationFocus.LEAVE:
        priority = ("vacation_balance", "sick_leave_balance", "net_salary")
    else:
        priority = ("net_salary", "gross_salary", "base_salary", "total_deductions")

    rank = {key: index for index, key in enumerate(priority)}
    return sorted(material, key=lambda d: (rank.get(d.field_key, 100), d.field_key))


def _synthesize_he(
    *,
    focus: InvestigationFocus,
    target: PeriodRef,
    comparison: PeriodRef,
    deltas: list[LineItemDelta],
) -> str:
    target_label = period_label(target, locale="he")
    comparison_label = period_label(comparison, locale="he")
    ordered = _ordered_deltas(deltas, focus=focus)
    parts: list[str] = [
        f"השוויתי את תלוש {target_label} לתלוש {comparison_label}."
    ]

    bridge = _causal_bridge_he(focus=focus, deltas=ordered)
    if bridge:
        parts.append(bridge)
        skip_keys = {"gross_salary"}
        if focus == InvestigationFocus.PENSION:
            skip_keys.update({"pension_employee", "pension_employer"})
        elif focus == InvestigationFocus.DEDUCTIONS:
            skip_keys.update(
                {
                    "total_deductions",
                    "income_tax",
                    "national_insurance",
                    "health_tax",
                    "pension_employee",
                }
            )
        extras = [
            _delta_sentence_he(delta)
            for delta in ordered
            if delta.field_key not in skip_keys
        ]
        extras = [sentence for sentence in extras if sentence][:4]
        if extras:
            parts.append("בנוסף: " + "; ".join(extras) + ".")
    elif not ordered:
        parts.append(
            f"לא מצאתי שינוי מהותי בפריטים הרלוונטיים ל{_FOCUS_HE.get(focus, 'השאלה')}."
        )
    else:
        sentences = [
            sentence
            for sentence in (_delta_sentence_he(delta) for delta in ordered[:6])
            if sentence
        ]
        if sentences:
            parts.append(sentences[0] + ".")
            if len(sentences) > 1:
                parts.append("בנוסף, " + "; ".join(sentences[1:]) + ".")

    parts.append(
        "ההסבר מבוסס על שדות התלוש וממצאי הבדיקה השמורים במערכת בלבד, "
        "בלי חישוב מחדש של מס או שכר."
    )
    return " ".join(parts)


def _synthesize_en(
    *,
    focus: InvestigationFocus,
    target: PeriodRef,
    comparison: PeriodRef,
    deltas: list[LineItemDelta],
) -> str:
    target_label = period_label(target, locale="en")
    comparison_label = period_label(comparison, locale="en")
    ordered = _ordered_deltas(deltas, focus=focus)
    parts = [
        f"I compared your {target_label} payslip with {comparison_label}."
    ]
    if not ordered:
        parts.append("I did not find material changes in the compared line items.")
    else:
        sentences = [
            sentence
            for sentence in (_delta_sentence_en(delta) for delta in ordered[:6])
            if sentence
        ]
        if sentences:
            parts.append(sentences[0] + ".")
            if len(sentences) > 1:
                parts.append("Also, " + "; ".join(s[0].lower() + s[1:] for s in sentences[1:]) + ".")
    parts.append(
        "This explanation uses stored payslip fields and validation findings only; "
        "it does not recalculate tax or salary rules."
    )
    return " ".join(parts)


def _synthesize_ar(
    *,
    focus: InvestigationFocus,
    target: PeriodRef,
    comparison: PeriodRef,
    deltas: list[LineItemDelta],
) -> str:
    ordered = _ordered_deltas(deltas, focus=focus)
    parts = [
        f"قارنت قسيمة {target.key} مع {comparison.key}."
    ]
    if not ordered:
        parts.append("لم أجد فروقات جوهرية في البنود المقارنة.")
    else:
        for delta in ordered[:5]:
            prior = delta.prior_value or "—"
            current = delta.current_value or "—"
            parts.append(f"{delta.field_key} تغيّر من {prior} إلى {current}.")
    parts.append(
        "يعتمد هذا الشرح على حقول القسيمة ونتائج التحقق المخزّنة فقط، "
        "دون إعادة احتساب الضرائب أو قواعد الأجر."
    )
    return " ".join(parts)


def synthesize_explained(
    *,
    locale: str,
    focus: InvestigationFocus,
    target: PeriodRef,
    comparison: PeriodRef,
    deltas: list[LineItemDelta],
    findings_messages: list[str] | None = None,
    enrichment_notes: str | None = None,
    message: str = "",
) -> str:
    """Build a natural, locale-matched answer from deterministic deltas only."""
    del findings_messages, enrichment_notes  # keep signature stable; avoid raw internals
    lang = resolve_response_locale(message=message, locale=locale)
    if lang == "en":
        return _synthesize_en(
            focus=focus,
            target=target,
            comparison=comparison,
            deltas=deltas,
        )
    if lang == "ar":
        return _synthesize_ar(
            focus=focus,
            target=target,
            comparison=comparison,
            deltas=deltas,
        )
    return _synthesize_he(
        focus=focus,
        target=target,
        comparison=comparison,
        deltas=deltas,
    )


def outcome_requires_review(outcome: InvestigationOutcome) -> bool:
    return outcome in {
        InvestigationOutcome.NEEDS_USER_INPUT,
        InvestigationOutcome.INSUFFICIENT_EVIDENCE,
    }
