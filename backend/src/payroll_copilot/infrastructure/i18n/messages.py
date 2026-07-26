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
    "validation.sanity.national_id.not_digits": {
        "he": "מספר תעודת הזהות חייב להכיל ספרות בלבד.",
        "en": "National ID must contain digits only.",
        "ar": "يجب أن يحتوي رقم الهوية على أرقام فقط.",
    },
    "validation.sanity.national_id.length": {
        "he": "מספר תעודת הזהות חייב להיות בן 9 ספרות.",
        "en": "National ID must be exactly 9 digits.",
        "ar": "يجب أن يتكون رقم الهوية من 9 أرقام بالضبط.",
    },
    "validation.sanity.national_id.checksum": {
        "he": "מספר תעודת הזהות נכשל בבדיקת תקינות.",
        "en": "National ID failed the checksum check.",
        "ar": "فشل رقم الهوية في فحص المجموع الاختباري.",
    },
    "validation.sanity.employee_name.numeric": {
        "he": "שם העובד אינו יכול להיות מספרי בלבד.",
        "en": "Employee name cannot be digits only.",
        "ar": "لا يمكن أن يكون اسم الموظف أرقامًا فقط.",
    },
    "validation.sanity.employee_name.no_letters": {
        "he": "שם העובד חייב לכלול אותיות.",
        "en": "Employee name must include letters.",
        "ar": "يجب أن يتضمن اسم الموظف أحرفًا.",
    },
    "validation.sanity.employee_name.too_short": {
        "he": "שם העובד קצר מדי מכדי להיות תקין.",
        "en": "Employee name is too short to be valid.",
        "ar": "اسم الموظف قصير جدًا ليكون صالحًا.",
    },
    "validation.sanity.employee_name.structure": {
        "he": "שם העובד במבנה לא תקין.",
        "en": "Employee name has an invalid structure.",
        "ar": "بنية اسم الموظف غير صالحة.",
    },
    "validation.sanity.pay_period.unparseable": {
        "he": "תקופת השכר אינה בפורמט מזוהה.",
        "en": "Payroll period is not in a recognized format.",
        "ar": "فترة الرواتب ليست بتنسيق معروف.",
    },
    "validation.sanity.pay_period.month": {
        "he": "חודש תקופת השכר אינו תקין.",
        "en": "Payroll period month is not valid.",
        "ar": "شهر فترة الرواتب غير صالح.",
    },
    "validation.sanity.pay_period.year": {
        "he": "שנת תקופת השכר אינה תקינה.",
        "en": "Payroll period year is not valid.",
        "ar": "سنة فترة الرواتب غير صالحة.",
    },
    "validation.sanity.employment_start_date.invalid": {
        "he": "תאריך תחילת העבודה אינו תאריך לוח שנה תקין.",
        "en": "Employment start date is not a valid calendar date.",
        "ar": "تاريخ بدء العمل ليس تاريخًا تقويميًا صالحًا.",
    },
    "validation.sanity.net_exceeds_gross": {
        "he": "השכר נטו גבוה מהשכר ברוטו על התלוש.",
        "en": "Net salary exceeds gross salary on this payslip.",
        "ar": "صافي الراتب يتجاوز إجمالي الراتب في قسيمة الراتب.",
    },
    "validation.sanity.required_field_missing": {
        "he": "שדה חובה חסר בתלוש.",
        "en": "A required payslip field is missing.",
        "ar": "حقل مطلوب في قسيمة الراتب مفقود.",
    },
    "validation.sanity.employment_type.unrecognized": {
        "he": "סוג ההעסקה בתלוש אינו מזוהה.",
        "en": "Employment type on the payslip is not recognized.",
        "ar": "نوع التوظيف في قسيمة الراتب غير معروف.",
    },
    "validation.employee.national_id.mismatch": {
        "he": "מספר תעודת הזהות בתלוש אינו תואם לרשומת העובד.",
        "en": "National ID on the payslip does not match the employee record.",
        "ar": "رقم الهوية في قسيمة الراتب لا يطابق سجل الموظف.",
    },
    "validation.employee.name.mismatch": {
        "he": "שם העובד בתלוש אינו תואם לרשומת העובד.",
        "en": "Employee name on the payslip does not match the employee record.",
        "ar": "اسم الموظف في قسيمة الراتب لا يطابق سجل الموظف.",
    },
    "validation.employee.employee_number.mismatch": {
        "he": "מספר העובד בתלוש אינו תואם לרשומת העובד.",
        "en": "Employee number on the payslip does not match the employee record.",
        "ar": "رقم الموظف في قسيمة الراتب لا يطابق سجل الموظف.",
    },
    "validation.employee.employment_start_date.mismatch": {
        "he": "תאריך תחילת העבודה בתלוש אינו תואם לרשומת העובד. (ממצא היסטורי; ההשוואה אינה רצה עוד.)",
        "en": "Employment start date on the payslip does not match the employee record. (Historical finding; this comparison is no longer run.)",
        "ar": "تاريخ بدء العمل في قسيمة الراتب لا يطابق سجل الموظف. (نتيجة تاريخية؛ لم تعد تُجرى هذه المقارنة.)",
    },
    "validation.employee.employment_type.mismatch": {
        "he": "סוג ההעסקה בתלוש אינו תואם לרשומת העובד.",
        "en": "Employment type on the payslip does not match the employee record.",
        "ar": "نوع التوظيف في قسيمة الراتب لا يطابق سجل الموظف.",
    },
    "validation.employee.pay_period.mismatch": {
        "he": "תקופת השכר בתלוש אינה תואמת לחודש שנבחר.",
        "en": "Payroll period on the payslip does not match the selected month.",
        "ar": "فترة الرواتب في قسيمة الراتب لا تطابق الشهر المحدد.",
    },
    "validation.contract.employment_commencement_date.mismatch": {
        "he": "תאריך תחילת העבודה בתלוש אינו תואם לתנאי ההעסקה המאושרים.",
        "en": "Employment start date on the payslip does not match confirmed employment terms.",
        "ar": "تاريخ بدء العمل في قسيمة الراتب لا يطابق شروط التوظيف المؤكدة.",
    },
    "validation.contract.salary_basis.mismatch": {
        "he": "בסיס חישוב השכר בתלוש אינו תואם לתנאי ההעסקה המאושרים.",
        "en": "Salary calculation basis on the payslip does not match confirmed employment terms.",
        "ar": "أساس حساب الراتب في القسيمة لا يطابق شروط التوظيف المؤكدة.",
    },
    "validation.contract.hourly_rate.mismatch": {
        "he": "השכר השעתי בתלוש אינו תואם לשכר השעתי החוזי המאושר.",
        "en": "Hourly rate on the payslip does not match the confirmed contractual hourly rate.",
        "ar": "الأجر بالساعة في القسيمة لا يطابق الأجر التعاقدي المؤكد بالساعة.",
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
    "validation.sanity.national_id.not_digits": {
        "he": "בדיקת מבנה תעודת זהות על בסיס הספרות שחולצו מהתלוש בלבד.",
        "en": "National ID structure check based only on digits extracted from the payslip.",
        "ar": "فحص بنية رقم الهوية استنادًا إلى الأرقام المستخرجة من قسيمة الراتب فقط.",
    },
    "validation.sanity.national_id.length": {
        "he": "תעודת זהות ישראלית מיוצגת כ־9 ספרות לאחר נירמול.",
        "en": "An Israeli National ID is represented as 9 digits after normalization.",
        "ar": "يُمثَّل رقم الهوية الإسرائيلي بـ 9 أرقام بعد التطبيع.",
    },
    "validation.sanity.national_id.checksum": {
        "he": "בדיקת ספרת ביקורת סטנדרטית לתעודת זהות ישראלית — ללא השוואה לפרופיל.",
        "en": "Standard Israeli ID checksum — no comparison to an employee profile.",
        "ar": "مجموع اختباري قياسي لرقم الهوية الإسرائيلي — دون مقارنة بملف الموظف.",
    },
    "validation.sanity.employee_name.numeric": {
        "he": "שמות עובדים חייבים לכלול אותיות בשפות הנתמכות — לא ספרות בלבד.",
        "en": "Employee names must include letters in supported languages — not digits only.",
        "ar": "يجب أن تتضمن أسماء الموظفين أحرفًا باللغات المدعومة — وليس أرقامًا فقط.",
    },
    "validation.sanity.employee_name.no_letters": {
        "he": "הערך שחולץ לשם אינו כולל אותיות Unicode.",
        "en": "The extracted name value does not include Unicode letters.",
        "ar": "قيمة الاسم المستخرجة لا تتضمن أحرف Unicode.",
    },
    "validation.sanity.employee_name.too_short": {
        "he": "שם קצר מדי נחשב בלתי סביר כשם אדם.",
        "en": "A name this short is not a plausible person name.",
        "ar": "اسم بهذا القصر ليس اسم شخص معقولًا.",
    },
    "validation.sanity.employee_name.structure": {
        "he": "בדיקת מבנה שם על התלוש בלבד — ללא השוואה לפרופיל.",
        "en": "Name structure check on the payslip only — no profile comparison.",
        "ar": "فحص بنية الاسم على قسيمة الراتب فقط — دون مقارنة بالملف.",
    },
    "validation.sanity.pay_period.unparseable": {
        "he": "הערך קיים אך לא ניתן לפרש אותו לחודש ושנה.",
        "en": "A period value is present but could not be parsed into month and year.",
        "ar": "قيمة الفترة موجودة لكن تعذر تحليلها إلى شهر وسنة.",
    },
    "validation.sanity.pay_period.month": {
        "he": "חודש בתקופת שכר חייב להיות בין 1 ל־12.",
        "en": "A payroll period month must be between 1 and 12.",
        "ar": "يجب أن يكون شهر فترة الرواتب بين 1 و 12.",
    },
    "validation.sanity.pay_period.year": {
        "he": "שנת תקופת השכר מחוץ לטווח המסמך המקובל במערכת.",
        "en": "Payroll period year is outside the document range used by the system.",
        "ar": "سنة فترة الرواتب خارج النطاق المستندي المستخدم في النظام.",
    },
    "validation.sanity.employment_start_date.invalid": {
        "he": "התאריך אינו תאריך לוח שנה תקין לפי הפורמטים הנתמכים.",
        "en": "The date is not a valid calendar date in supported formats.",
        "ar": "التاريخ ليس تاريخًا تقويميًا صالحًا بالتنسيقات المدعومة.",
    },
    "validation.sanity.net_exceeds_gross": {
        "he": "עקביות פנימית בתלוש: נטו אינו יכול לעלות על ברוטו כאשר שניהם קיימים.",
        "en": "Internal payslip coherence: net cannot exceed gross when both are present.",
        "ar": "اتساق داخلي في قسيمة الراتب: لا يمكن أن يتجاوز الصافي الإجمالي عند وجود كليهما.",
    },
    "validation.sanity.required_field_missing": {
        "he": "שדה שמסומן כנדרש בתלוש חסר בנתונים המאושרים — אינו חוסם שמירה.",
        "en": "A field marked required on the payslip is missing from confirmed data — does not block persistence.",
        "ar": "حقل مُعلَم كمطلوب في قسيمة الراتب مفقود من البيانات المؤكدة — ولا يمنع الحفظ.",
    },
    "validation.sanity.employment_type.unrecognized": {
        "he": "הערך קיים אך אינו תואם לסוגי העסקה הנתמכים במערכת — ללא המרה אוטומטית.",
        "en": "A value is present but does not match supported employment types — no automatic conversion.",
        "ar": "القيمة موجودة لكنها لا تطابق أنواع التوظيف المدعومة — دون تحويل تلقائي.",
    },
    "validation.employee.national_id.mismatch": {
        "he": "השוואה בין תעודת הזהות שחולצה מהתלוש לבין הרשומה המורשית של העובד.",
        "en": "Compared the National ID extracted from the payslip to the authorized employee record.",
        "ar": "تمت مقارنة رقم الهوية المستخرج من قسيمة الراتب بسجل الموظف المصرح به.",
    },
    "validation.employee.name.mismatch": {
        "he": "השוואת שם דטרמיניסטית (סדר אסיים) בין התלוש לרשומת העובד.",
        "en": "Deterministic order-insensitive name comparison between payslip and employee record.",
        "ar": "مقارنة اسم حتمية غير حساسة للترتيب بين قسيمة الراتب وسجل الموظف.",
    },
    "validation.employee.employee_number.mismatch": {
        "he": "השוואת מזהה שכר/מערכת — לא תעודת זהות.",
        "en": "Payroll/system identifier comparison — not National ID.",
        "ar": "مقارنة معرّف الرواتب/النظام — وليس رقم الهوية.",
    },
    "validation.employee.employment_start_date.mismatch": {
        "he": "ממצא היסטורי בלבד: ההשוואה לתאריך תחילת חוזה ברשומת העובד הוסרה — השדה אינו מקור סמכותי לתחילת העסקה.",
        "en": "Historical finding only: comparison to employee-record contract_start_date was removed — that field is not authoritative employment commencement.",
        "ar": "نتيجة تاريخية فقط: أُزيلت المقارنة مع contract_start_date في سجل الموظف — هذا الحقل ليس بدء عمل موثوقًا.",
    },
    "validation.employee.employment_type.mismatch": {
        "he": "השוואה רק כאשר שני הצדדים משתמשים באותו קטלוג סוגי העסקה.",
        "en": "Compared only when both sides use the same employment-type catalog.",
        "ar": "تمت المقارنة فقط عندما يستخدم الطرفان نفس كتالوج أنواع التوظيف.",
    },
    "validation.employee.pay_period.mismatch": {
        "he": "בדיקת שקיפות מול חודש העבודה שנבחר — אינה מחליפה את שערי Move/Keep/Cancel.",
        "en": "Transparency check against the selected workspace month — does not replace Move/Keep/Cancel gates.",
        "ar": "فحص شفافية مقابل شهر مساحة العمل المحدد — ولا يستبدل بوابات Move/Keep/Cancel.",
    },
    "validation.contract.employment_commencement_date.mismatch": {
        "he": "השוואה לתאריך תחילת העסקה המקורי בתנאי העסקה מאושרים — לא לתאריך יצירת רשומה במערכת.",
        "en": "Compared to confirmed original employment commencement — never system create/onboarding dates.",
        "ar": "تمت المقارنة مع تاريخ بدء التوظيف الأصلي المؤكد — وليس تواريخ إنشاء/انضمام النظام.",
    },
    "validation.contract.salary_basis.mismatch": {
        "he": "השוואת בסיס חישוב שכר (חודשי/שעתי/יומי) — לא סוג העסקה.",
        "en": "Compared salary calculation basis (monthly/hourly/daily) — not employment type.",
        "ar": "مقارنة أساس حساب الراتب (شهري/بالساعة/يومي) — وليس نوع التوظيف.",
    },
    "validation.contract.hourly_rate.mismatch": {
        "he": "השוואת שכר שעתי בתלוש מול שכר שעתי חוזי מאושר.",
        "en": "Compared payslip hourly rate to confirmed contractual hourly rate.",
        "ar": "تمت مقارنة الأجر بالساعة في القسيمة مع الأجر التعاقدي المؤكد بالساعة.",
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
