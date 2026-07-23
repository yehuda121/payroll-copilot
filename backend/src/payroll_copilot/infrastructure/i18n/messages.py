"""User-facing message catalogs for he / en / ar.

Deterministic validation decisions stay language-independent. These catalogs only
localize display text for API responses and assistant safe templates.
"""

from __future__ import annotations

from payroll_copilot.infrastructure.i18n.locale import normalize_locale

# message_key -> locale -> display text
FINDING_MESSAGES: dict[str, dict[str, str]] = {
    "validation.overtime.daily_limit_exceeded": {
        "he": "שעות נוספות חורגות מהמגבלה היומית המותרת.",
        "en": "Overtime exceeds the allowed daily limit.",
        "ar": "تجاوزت ساعات العمل الإضافية الحد اليومي المسموح.",
    },
    "validation.minimum_wage.below_threshold": {
        "he": "השכר נמוך משכר המינימום.",
        "en": "Pay is below the minimum wage threshold.",
        "ar": "الأجر أقل من الحد الأدنى للأجور.",
    },
    "validation.pension.insufficient_contribution": {
        "he": "הפרשות הפנסיה נמוכות מהנדרש.",
        "en": "Pension contribution is below the required level.",
        "ar": "مساهمة التقاعد أقل من المستوى المطلوب.",
    },
    "validation.youth.below_minimum_age": {
        "he": "גיל העובד נמוך מהמינימום החוקי.",
        "en": "Employee age is below the legal minimum.",
        "ar": "عمر الموظف أقل من الحد الأدنى القانوني.",
    },
    "validation.department.intern_hours_exceeded": {
        "he": "שעות המתמחה חורגות ממגבלת המחלקה.",
        "en": "Intern hours exceed the department limit.",
        "ar": "ساعات المتدرب تتجاوز حد القسم.",
    },
    "validation.department.lawyers_overtime_cap": {
        "he": "שעות נוספות לעורכי דין חורגות מהתקרה המחלקתית.",
        "en": "Lawyer overtime exceeds the department cap.",
        "ar": "ساعات العمل الإضافية للمحامين تتجاوز سقف القسم.",
    },
    "validation.historical.salary_drift": {
        "he": "זוהתה סטיית שכר חריגה בהשוואה להיסטוריה.",
        "en": "Unusual salary drift was detected versus history.",
        "ar": "تم اكتشاف انحراف غير معتاد في الراتب مقارنة بالتاريخ.",
    },
    "validation.missing_data": {
        "he": "חסרים נתונים הנדרשים להשלמת הבדיקה.",
        "en": "Required data is missing to complete this check.",
        "ar": "البيانات المطلوبة لإكمال هذا الفحص غير موجودة.",
    },
}

FINDING_EXPLANATIONS: dict[str, dict[str, str]] = {
    "validation.overtime.daily_limit_exceeded": {
        "he": "המנוע הזיהוי חריגה ממגבלת השעות הנוספות לפי הכלל המוגדר.",
        "en": "The engine detected overtime above the configured daily rule limit.",
        "ar": "اكتشف المحرك تجاوز ساعات العمل الإضافية للحد اليومي المحدد في القاعدة.",
    },
    "validation.minimum_wage.below_threshold": {
        "he": "השוואה לשכר המינימום לפי הכלל הקבוע בקונפיגורציה.",
        "en": "Compared against the configured minimum-wage rule.",
        "ar": "تمت المقارنة مع قاعدة الحد الأدنى للأجور المحددة في الإعدادات.",
    },
    "validation.pension.insufficient_contribution": {
        "he": "הפרשות הפנסיה נמוכות מהשיעור/הסכום הנדרש בכלל.",
        "en": "Pension contributions are below the rate/amount required by the rule.",
        "ar": "مساهمات التقاعد أقل من النسبة/المبلغ المطلوب في القاعدة.",
    },
    "validation.youth.below_minimum_age": {
        "he": "גיל העובד אינו עומד בדרישת המינימום לכלל זה.",
        "en": "Employee age does not meet the minimum required by this rule.",
        "ar": "عمر الموظف لا يستوفي الحد الأدنى المطلوب لهذه القاعدة.",
    },
    "validation.department.intern_hours_exceeded": {
        "he": "חריגה ממגבלת השעות של פרופיל מחלקת מתמחים.",
        "en": "Hours exceed the intern department profile limit.",
        "ar": "تجاوزت الساعات حد ملف قسم المتدربين.",
    },
    "validation.department.lawyers_overtime_cap": {
        "he": "חריגה מתקרת השעות הנוספות לפרופיל עורכי דין.",
        "en": "Overtime exceeds the lawyers department profile cap.",
        "ar": "تجاوزت ساعات العمل الإضافية سقف ملف قسم المحامين.",
    },
    "validation.historical.salary_drift": {
        "he": "השוואה להיסטוריית שכר זיהתה סטייה חריגה.",
        "en": "Historical salary comparison found unusual drift.",
        "ar": "أظهرت مقارنة الرواتب التاريخية انحرافًا غير معتاد.",
    },
    "validation.missing_data": {
        "he": "לא ניתן להשלים את הבדיקה בלי השדות החסרים.",
        "en": "This check cannot finish without the missing fields.",
        "ar": "لا يمكن إكمال هذا الفحص دون الحقول المفقودة.",
    },
}

SCOPE_LABELS: dict[str, dict[str, str]] = {
    "payroll_rules": {
        "he": "כללי שכר",
        "en": "Payroll Rules",
        "ar": "قواعد الرواتب",
    },
    "attendance": {
        "he": "בדיקת נוכחות",
        "en": "Attendance Validation",
        "ar": "التحقق من الحضور",
    },
    "employment_agreement": {
        "he": "בדיקת הסכם העסקה",
        "en": "Employment Agreement Validation",
        "ar": "التحقق من عقد العمل",
    },
    "tax_benefits": {
        "he": "הטבות מס",
        "en": "Tax Benefits",
        "ar": "المزايا الضريبية",
    },
    "historical_comparison": {
        "he": "השוואה היסטורית",
        "en": "Historical Comparison",
        "ar": "المقارنة التاريخية",
    },
}

SCOPE_REASONS: dict[str, dict[str, str]] = {
    "extraction_not_connected": {
        "he": "חילוץ מסמכים עדיין לא מחובר. הכללים רצו על הקשר של מנוע הבדיקה בלבד.",
        "en": "Document extraction is not yet connected. Rules ran on the validation engine context only.",
        "ar": "استخراج المستندات غير متصل بعد. عملت القواعد على سياق محرك التحقق فقط.",
    },
    "payroll_extraction_connected": {
        "he": "כללי שכר רצו על נתונים שחולצו ונבדקו מהתלוש שהעליתם.",
        "en": "Payroll rules ran on fields extracted and reviewed from your uploaded payslip.",
        "ar": "عملت قواعد الرواتب على الحقول المستخرجة والمراجعة من كشف الراتب المرفوع.",
    },
    "payroll_core_fields_incomplete": {
        "he": "חלק משדות הליבה חסרים או לא ניתנים לשימוש. היכן שחסר מידע התוצאה היא 'לא ניתן לאמת'.",
        "en": "Some core fields are missing or unusable. Where data is unavailable the result is Unable to verify.",
        "ar": "بعض الحقول الأساسية ناقصة أو غير قابلة للاستخدام. حيثما تكون البيانات غير متوفرة تكون النتيجة تعذر التحقق.",
    },
    "attendance_not_uploaded": {
        "he": "דוח נוכחות לא הועלה.",
        "en": "Attendance report not uploaded.",
        "ar": "لم يتم رفع تقرير الحضور.",
    },
    "attendance_uploaded_not_connected": {
        "he": "דוח נוכחות הועלה, אך חילוץ נוכחות והצלבה עדיין לא מחוברים.",
        "en": "Attendance report uploaded, but attendance extraction and cross-check are not yet connected.",
        "ar": "تم رفع تقرير الحضور، لكن استخراج الحضور والمقارنة غير متصلين بعد.",
    },
    "contract_not_uploaded": {
        "he": "הסכם העסקה לא הועלה.",
        "en": "Employment agreement not uploaded.",
        "ar": "لم يتم رفع عقد العمل.",
    },
    "contract_uploaded_not_connected": {
        "he": "הסכם העסקה הועלה, אך ניתוח חוזה עדיין לא מחובר.",
        "en": "Employment agreement uploaded, but contract analysis is not yet connected.",
        "ar": "تم رفع عقد العمل، لكن تحليل العقد غير متصل بعد.",
    },
    "id_not_uploaded": {
        "he": "תעודת זהות לא הועלתה.",
        "en": "Israeli ID was not uploaded.",
        "ar": "لم يتم رفع بطاقة الهوية الإسرائيلية.",
    },
    "id_uploaded_not_connected": {
        "he": "תעודת זהות הועלתה, אך בדיקות מס התלויות בזהות עדיין לא מחוברות.",
        "en": "Israeli ID uploaded, but identity-dependent tax checks are not yet connected.",
        "ar": "تم رفع بطاقة الهوية، لكن الفحوصات الضريبية المعتمدة على الهوية غير متصلة بعد.",
    },
    "historical_not_available": {
        "he": "נתוני שכר היסטוריים אינם זמינים.",
        "en": "Historical payroll data is not available.",
        "ar": "بيانات الرواتب التاريخية غير متوفرة.",
    },
    "all_evidence_available": {
        "he": "כל הראיות הנדרשות להיקף הבדיקה הנתמך כרגע זמינות.",
        "en": "All required evidence for the currently supported validation scope is available.",
        "ar": "جميع الأدلة المطلوبة لنطاق التحقق المدعوم حاليًا متوفرة.",
    },
}

ASSISTANT_STRINGS: dict[str, dict[str, str]] = {
    "greeting": {
        "he": (
            "שלום! אני Payroll Copilot. אפשר לעזור בנושאי שכר, תלושים, נוכחות, "
            "הסכמי העסקה, דיני עבודה בישראל ודוחות בדיקה. במה תרצו לבדוק?"
        ),
        "en": (
            "Hi! I'm Payroll Copilot. I can help with payroll, payslips, "
            "attendance, employment contracts, Israeli labor law, and validation "
            "reports. What would you like to check?"
        ),
        "ar": (
            "مرحبًا! أنا Payroll Copilot. يمكنني المساعدة في الرواتب وكشوف الرواتب "
            "والحضور وعقود العمل وقانون العمل الإسرائيلي وتقارير التحقق. بماذا تريد الفحص؟"
        ),
    },
    "template_prefix": {
        "he": "על סמך המידע הזמין ב-Payroll Copilot",
        "en": "Based on the information available in Payroll Copilot",
        "ar": "استنادًا إلى المعلومات المتوفرة في Payroll Copilot",
    },
    "limited_no_source": {
        "he": "לא מצאתי מידע מדויק מספיק לשאלה זו כרגע.",
        "en": "I could not find precise enough information for this question right now.",
        "ar": "لم أجد معلومات دقيقة بما يكفي لهذا السؤال حاليًا.",
    },
    "blocked": {
        "he": "לא ניתן לעבד את הבקשה הזו.",
        "en": "This request could not be processed.",
        "ar": "تعذر معالجة هذا الطلب.",
    },
    "disclaimer": {
        "he": (
            "\n\nהערה: עוזר זה מספק הסברים מידעיים בלבד ואינו מהווה ייעוץ משפטי או מקצועי. "
            "הכרעה סופית לגבי עמידה בכללים מתבצעת בבדיקת Payroll Copilot."
        ),
        "en": (
            "\n\nNote: This assistant provides informational explanations only and is not "
            "legal or professional advice. Final compliance decisions are made by "
            "Payroll Copilot validation."
        ),
        "ar": (
            "\n\nملاحظة: يقدم هذا المساعد تفسيرات معلوماتية فقط وليس استشارة قانونية أو مهنية. "
            "تُتخذ قرارات الامتثال النهائية عبر تحقق Payroll Copilot."
        ),
    },
    "limited_full": {
        "he": (
            "לא מצאתי מידע מדויק מספיק לשאלה זו כרגע. אוכל לתת הכוונה כללית בלבד: "
            "Payroll Copilot עוזר לבדוק תלושי שכר ומסמכים תומכים, "
            "והעוזר מסביר ומנווט בלי לקבוע עמידה בחוק. "
            "העלו תלוש והריצו בדיקה כדי לקבל תוצאה סופית. "
            "לא אמציא סכומים, תעריפים, תאריכים או נוסחאות חוקיות."
        ),
        "en": (
            "I could not find precise enough information for this question right now. "
            "I can only give general guidance: Payroll Copilot helps review payslips and "
            "supporting documents, while this assistant explains and guides without "
            "deciding legal compliance. "
            "Upload a payslip and run validation for a final outcome. "
            "I will not invent exact legal amounts, rates, dates, or formulas."
        ),
        "ar": (
            "لم أجد معلومات دقيقة بما يكفي لهذا السؤال حاليًا. يمكنني تقديم إرشاد عام فقط: "
            "يساعد Payroll Copilot في مراجعة كشوف الرواتب والمستندات الداعمة، "
            "وهذا المساعد يشرح ويوجّه دون تحديد الامتثال القانوني. "
            "ارفع كشف راتب وشغّل التحقق للحصول على نتيجة نهائية. "
            "لن أخترع مبالغ أو نسبًا أو تواريخ أو صيغًا قانونية دقيقة."
        ),
    },
    "limited_documents_needed": {
        "he": (
            "לבדיקת תלוש ב-Payroll Copilot נדרש תלוש שכר. "
            "אפשר להוסיף אופציונלית דוח נוכחות, הסכם העסקה ותעודת זהות. "
            "הבדיקה הסופית מתבצעת לאחר ההעלאה — לא על ידי עוזר זה."
        ),
        "en": (
            "To validate a payslip in Payroll Copilot you need a payslip upload. "
            "Optionally add an attendance report, employment agreement, and Israeli ID. "
            "Final validation runs after upload — not by this assistant."
        ),
        "ar": (
            "للتحقق من كشف راتب في Payroll Copilot يلزم رفع كشف الراتب. "
            "يمكن اختياريًا إضافة تقرير حضور وعقد عمل وبطاقة هوية إسرائيلية. "
            "يتم التحقق النهائي بعد الرفع — وليس بواسطة هذا المساعد."
        ),
    },
    "limited_overtime_payslip": {
        "he": (
            "באופן כללי, שעות נוספות אמורות להופיע בתלוש כפריט נפרד (שעות/סכום) לפי מדיניות השכר. "
            "לא אציין כאן תעריפים או מגבלות חוקיות מדויקות בלי מידע מספיק. "
            "להכרעה סופית העלו תלוש והריצו בדיקה ב-Payroll Copilot."
        ),
        "en": (
            "In general, overtime should appear on a payslip as a distinct line item "
            "(hours and/or amount) according to payroll policy. "
            "I will not state exact legal rates or limits without sufficient information. "
            "For a final decision, upload a payslip and run Payroll Copilot validation."
        ),
        "ar": (
            "عمومًا، يجب أن تظهر ساعات العمل الإضافية في كشف الراتب كبند مستقل "
            "(ساعات و/أو مبلغ) وفق سياسة الرواتب. "
            "لن أذكر نسبًا أو حدودًا قانونية دقيقة دون معلومات كافية. "
            "للحسم النهائي، ارفع كشف راتب وشغّل تحقق Payroll Copilot."
        ),
    },
    "limited_warning_vs_critical": {
        "he": (
            "ב-Payroll Copilot, אזהרה מסמנת סטטוס שדורש בדיקה אך אינו חוסם בהכרח. "
            "ממצא קריטי מסמן סיכון גבוה יותר הדורש טיפול לפני אישור תשלום. "
            "הסיווג נקבע בבדיקת המערכת על סמך הכללים — לא על ידי עוזר זה."
        ),
        "en": (
            "In Payroll Copilot, a warning means an item needs review but is not necessarily blocking. "
            "A critical finding marks higher risk that should be addressed before approving payment. "
            "Severity is assigned by system validation from rule results — not by this assistant."
        ),
        "ar": (
            "في Payroll Copilot، التحذير يعني أن البند يحتاج مراجعة لكنه ليس بالضرورة حاجبًا. "
            "النتيجة الحرجة تشير إلى خطر أعلى يجب معالجته قبل الموافقة على الدفع. "
            "تُحدد الخطورة بواسطة تحقق النظام من نتائج القواعد — وليس بواسطة هذا المساعد."
        ),
    },
    "blocked_prompt_injection": {
        "he": "לא אוכל לעבד בקשה זו. אני מוגבל לסיוע בשכר, תלושים ודיני עבודה.",
        "en": (
            "I cannot process that request. I am limited to payroll, payslip, and "
            "labor-law assistance."
        ),
        "ar": "لا يمكنني معالجة هذا الطلب. أنا محدود بالمساعدة في الرواتب وكشوف الرواتب وقانون العمل.",
    },
    "blocked_off_topic": {
        "he": "אני יכול לעזור רק בשכר, תלושים, נוכחות, חוזים, דיני עבודה ושימוש ב-Payroll Copilot.",
        "en": (
            "I can only help with payroll, payslips, attendance, contracts, labor law, "
            "and Payroll Copilot usage."
        ),
        "ar": "يمكنني المساعدة فقط في الرواتب وكشوف الرواتب والحضور والعقود وقانون العمل واستخدام Payroll Copilot.",
    },
    "blocked_empty": {
        "he": "נא להזין שאלה הקשורה לשכר.",
        "en": "Please enter a payroll-related question.",
        "ar": "يرجى إدخال سؤال متعلق بالرواتب.",
    },
    "blocked_generic": {
        "he": "לא אוכל לעבד בקשה זו.",
        "en": "I cannot process that request.",
        "ar": "لا يمكنني معالجة هذا الطلب.",
    },
    "opening_labor_law": {
        "he": "על פי דיני העבודה בישראל:",
        "en": "According to Israeli labor law:",
        "ar": "وفقًا لقانون العمل الإسرائيلي:",
    },
    "opening_personal_payslip": {
        "he": "על פי התלוש שלך לתקופה {period}:",
        "en": "According to your payslip for {period}:",
        "ar": "وفقًا لكشف راتبك لفترة {period}:",
    },
    "opening_payroll_calculation": {
        "he": "על בסיס התלושים הרלוונטיים:",
        "en": "Based on the following payslips:",
        "ar": "بناءً على كشوف الرواتب التالية:",
    },
    "opening_validation": {
        "he": "על פי תוצאות הבדיקה הזמינות:",
        "en": "Based on the available validation results:",
        "ar": "بناءً على نتائج التحقق المتوفرة:",
    },
    "opening_conversation_history": {
        "he": "על בסיס השיחה שלנו עד כה:",
        "en": "Based on our previous conversation:",
        "ar": "بناءً على محادثتنا السابقة:",
    },
    "opening_document_explanation": {
        "he": "על פי המסמך הרלוונטי:",
        "en": "Based on the relevant document:",
        "ar": "بناءً على المستند ذي الصلة:",
    },
    "opening_general_payroll": {
        "he": "בנושא השכר:",
        "en": "Regarding payroll:",
        "ar": "بخصوص الرواتب:",
    },
}


def localize(catalog: dict[str, dict[str, str]], key: str, locale: str, *, fallback: str | None = None) -> str:
    lang = normalize_locale(locale)
    entry = catalog.get(key, {})
    if lang in entry:
        return entry[lang]
    if "en" in entry:
        return entry["en"]
    if "he" in entry:
        return entry["he"]
    return fallback if fallback is not None else key


def finding_message(message_key: str, locale: str) -> str:
    text = localize(FINDING_MESSAGES, message_key, locale, fallback="")
    if text:
        return text
    return message_key.replace(".", " ").replace("_", " ")


def finding_explanation(message_key: str, locale: str) -> str:
    text = localize(FINDING_EXPLANATIONS, message_key, locale, fallback="")
    if text:
        return text
    return finding_message(message_key, locale)


def scope_label(key: str, locale: str) -> str:
    return localize(SCOPE_LABELS, key, locale, fallback=key.replace("_", " ").title())


def scope_reason(reason_key: str, locale: str) -> str:
    return localize(SCOPE_REASONS, reason_key, locale, fallback=reason_key)


def assistant_text(key: str, locale: str) -> str:
    return localize(ASSISTANT_STRINGS, key, locale, fallback=key)
