# Seed Approval Table (OCR-only review)

> REVIEW ONLY — NOT APPROVED SEED DATA
>
> Parser output ignored (hallucinations rejected). No DB writes. No final seed file.

## How to review

1. Open the source PDF page listed for each slip.
2. For each field, set `review_status` to `CONFIRMED_FROM_OCR` only if the OCR value matches the printed slip.
3. Edit `ocr_raw` only to match exact printed text if OCR is wrong — or mark `UNREADABLE` / `CONFLICTING`.
4. Do **not** merge employees by name; confirm national IDs first.
5. National IDs are **masked** in this Markdown; full digits are in `seed_approval_table.json` (local).

## Summary

- Pages reviewed: **15**
- Proposed employee groups (by exact ID pending confirm): **7**
- Ungrouped pages: **1**
- Field statuses: `{"REVIEW_REQUIRED": 186, "MISSING": 57, "CONFLICTING": 7, "UNREADABLE": 5}`

## Proposed employee groups

| Employee key | National ID (masked) | Payslip keys | Names (OCR) | Basis |
|---|---|---|---|---|
| `emp_nid_d7c0b66f9cea` | 30****19 | `valid_payslips_valid_2026_06_multi_p01`, `invalid_payslips_invalid_2026_07_multi_p01` | סבירסקי אורית | exact_national_id_digits_pending_human_confirm |
| `emp_nid_21a7b7d1eead` | 31****98 | `valid_payslips_valid_2026_06_multi_p02`, `invalid_payslips_invalid_2026_07_multi_p02` | סבירסקי יונה לב | exact_national_id_digits_pending_human_confirm |
| `emp_nid_5d945bcea62c` | 33****46 | `valid_payslips_valid_2026_06_multi_p03`, `invalid_payslips_invalid_2026_07_multi_p03` | אביגיל תמר סבירסקי | exact_national_id_digits_pending_human_confirm |
| `emp_nid_17f2d60c389c` | 22****96 | `valid_payslips_valid_2026_06_multi_p04`, `invalid_payslips_invalid_2026_07_multi_p04` | יעקב ישראל סבירסקי | exact_national_id_digits_pending_human_confirm |
| `emp_nid_94329fe7354f` | 31****83 | `valid_payslips_valid_2026_06_multi_p05`, `invalid_payslips_invalid_2026_07_multi_p05` | שמולבי\ יהודה | exact_national_id_digits_pending_human_confirm |
| `emp_nid_fd0509db7499` | 15****52 | `valid_payslips_valid_2026_06_multi_p06`, `invalid_payslips_invalid_2026_07_multi_p06` | יעל ויטלין | exact_national_id_digits_pending_human_confirm |
| `emp_nid_9462ed1ce6ec` | 56****34 | `valid_payslips_valid_2026_06_multi_p07`, `invalid_payslips_invalid_2026_07_multi_p07` | רחל בנימלני | exact_national_id_digits_pending_human_confirm |
| `emp_ungrouped_valid_payslip_valid_2026_06_employee_001_p01` | — | `valid_payslip_valid_2026_06_employee_001_p01` |  | ungrouped_pending_review |

## `valid_payslips_valid_2026_06_multi_p01`

- **Proposed employee key:** `emp_nid_d7c0b66f9cea`
- **Source file:** `valid/payslips_valid_2026_06_multi.pdf`
- **Source page:** 1
- **Fixture intent:** `valid` (intent only — not a validation result)
- **OCR confidence:** 0.8689655172413793
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | סבירסקי אורית | — | סבירסקי אורית | p1_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 30****19 | 30****19 | 30****19 | p1_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p1_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6/26 | 6 | 6/26 | p1_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `payroll_year` | REVIEW_REQUIRED | 6/26 | 2026 | 6/26 | p1_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `base_salary` | REVIEW_REQUIRED | 8,000.00 | 8000.0 | 8,000.00 | p1_l56, p1_l58 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 8,872.30 | 8872.3 | 8,872.30 | p1_l79, p1_l78 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p1_l106, p1_l108 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | REVIEW_REQUIRED | 182.00 | 182.0 | 182.00 | p1_l21, p1_l22 | Hours candidate near label; verify against PDF (OCR often swaps columns). |
| `overtime_hours` | REVIEW_REQUIRED | 54.93 | 54.93 | 54.93 | p1_l70, p1_l71 | Nearest amount candidate to label 'שעות נוספות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `travel_reimbursement` | REVIEW_REQUIRED | 323.00 | 323.0 | 323.00 | p1_l63, p1_l64 | Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `income_tax` | REVIEW_REQUIRED | 8,000.00 | 8000.0 | 8,000.00 | p1_l54, p1_l53 | Nearest amount candidate to label 'מס הכנסה 14% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 162.00 | 162.0 | 162.00 | p1_l60, p1_l59 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 309.00 | 309.0 | 309.00 | p1_l65, p1_l66 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 54.93 | 54.93 | 54.93 | p1_l70, p1_l72 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | שעות נוספות; גילום | — | שעות נוספות; גילום | p1_l71, p1_l48 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6/26
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
התחלת עבודה
6 ותק-שנים:
"(0
סבירסקי אורית
ת"ז
30****19
182.00
182.00
ועות עבודה
מתוך:
מחלקה:
22.00
22.00
וימי עבודה
מתוך:
100.00
43.96
היקף משרה %
תע' שעה:
דרגה:
הלל
2 (דירה 3)
ק/סניף:
רוג':
חשבון:
אלעד
4080234
|מינימום לחודש:
לשעה:
6,443.85

```

</details>

## `valid_payslips_valid_2026_06_multi_p02`

- **Proposed employee key:** `emp_nid_21a7b7d1eead`
- **Source file:** `valid/payslips_valid_2026_06_multi.pdf`
- **Source page:** 2
- **Fixture intent:** `valid` (intent only — not a validation result)
- **OCR confidence:** 0.8700701754385964
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | סבירסקי יונה לב | — | סבירסקי יונה לב | p2_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 31****98 | 31****98 | 31****98 | p2_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p2_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6/26 | 6 | 6/26 | p2_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `payroll_year` | REVIEW_REQUIRED | 6/26 | 2026 | 6/26 | p2_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `base_salary` | REVIEW_REQUIRED | 7,500.00 | 7500.0 | 7,500.00 | p2_l53, p2_l56 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 7,839.00 | 7839.0 | 7,839.00 | p2_l73, p2_l72 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p2_l100, p2_l102 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | REVIEW_REQUIRED | 120.00 | 120.0 | 120.00 | p2_l21, p2_l22 | Hours candidate near label; verify against PDF (OCR often swaps columns). |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | REVIEW_REQUIRED | 22.60 | 22.6 | 22.60 | p2_l62, p2_l63 | Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `income_tax` | REVIEW_REQUIRED | 7,500.00 | 7500.0 | 7,500.00 | p2_l53, p2_l52 | Nearest amount candidate to label 'מס הכנסה 14% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 90.00 | 90.0 | 90.00 | p2_l58, p2_l57 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 256.00 | 256.0 | 256.00 | p2_l64, p2_l65 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 256.00 | 256.0 | 256.00 | p2_l64, p2_l66 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | גילום | — | גילום | p2_l47 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6/26
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
Nanna}‏ עבודה:
6 ותק-שנים:
"(0
סבירסקי יונה לב
ת"ז
31****98
120.00
120.00
ועות עבודה:
מתוך:
מחלקה:
15.00
15.00
ימי עבודה:
מתוך:
62.50
היקף משרה %
תע' שעה:
דרגה:
הלל
2 (דירה 3)
ק/סניף:
רוג':
חשבון:
אלעד
4080234
|מינימום לחודש:
לשעה:
לפי ימים
6
```

</details>

## `valid_payslips_valid_2026_06_multi_p03`

- **Proposed employee key:** `emp_nid_5d945bcea62c`
- **Source file:** `valid/payslips_valid_2026_06_multi.pdf`
- **Source page:** 3
- **Fixture intent:** `valid` (intent only — not a validation result)
- **OCR confidence:** 0.8707380073800738
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | אביגיל תמר סבירסקי | — | אביגיל תמר סבירסקי | p3_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 33****46 | 33****46 | 33****46 | p3_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p3_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6/26 | 6 | 6/26 | p3_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `payroll_year` | REVIEW_REQUIRED | 6/26 | 2026 | 6/26 | p3_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `base_salary` | REVIEW_REQUIRED | 6,442.80 | 6442.8 | 6,442.80 | p3_l53, p3_l56 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 6,765.80 | 6765.8 | 6,765.80 | p3_l70, p3_l69 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p3_l97, p3_l99 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | REVIEW_REQUIRED | 182.00 | 182.0 | 182.00 | p3_l21, p3_l22 | Hours candidate near label; verify against PDF (OCR often swaps columns). |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | REVIEW_REQUIRED | 323.00 | 323.0 | 323.00 | p3_l60, p3_l61 | Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `income_tax` | REVIEW_REQUIRED | 6,442.80 | 6442.8 | 6,442.80 | p3_l53, p3_l52 | Nearest amount candidate to label 'מס הכנסה 10% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p3_l58, p3_l57 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 323.00 | 323.0 | 323.00 | p3_l60, p3_l62 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 323.00 | 323.0 | 323.00 | p3_l60, p3_l63 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | גילום | — | גילום | p3_l47 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6/26
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
Nanna}‏ עבודה:
6 ותק-שנים:
"(0
אביגיל תמר סבירסקי
ת"ז
33****46
182.00
182.00
ועות עבודה:
מתוך:
מחלקה:
22.00
22.00
ימי עבודה:
מתוך:
35.40
היקף משרה %
תע' שעה:
דרגה:
הלל
32
ק/סניף:
דרוג :
חשבון:
אלעד
408
|מינימום לחודש:
לשעה:
לפי שעות
4,510.69

```

</details>

## `valid_payslips_valid_2026_06_multi_p04`

- **Proposed employee key:** `emp_nid_17f2d60c389c`
- **Source file:** `valid/payslips_valid_2026_06_multi.pdf`
- **Source page:** 4
- **Fixture intent:** `valid` (intent only — not a validation result)
- **OCR confidence:** 0.8703460207612457
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | יעקב ישראל סבירסקי | — | יעקב ישראל סבירסקי | p4_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 22****96 | 22****96 | 22****96 | p4_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p4_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6/26 | 6 | 6/26 | p4_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `payroll_year` | REVIEW_REQUIRED | 6/26 | 2026 | 6/26 | p4_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `base_salary` | REVIEW_REQUIRED | 10,000.00 | 10000.0 | 10,000.00 | p4_l51, p4_l53 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 12,246.04 | 12246.04 | 12,246.04 | p4_l76, p4_l75 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p4_l106, p4_l108 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | CONFLICTING | 182.00 | 182.0 | 182.00@p4_l21; 210.00@p4_l20; 22.00@p4_l25; 22.00@p4_l26 | p4_l21, p4_l20, p4_l25, p4_l26, p4_l22 | Multiple hour-like numbers near hours label — confirm which is reported vs base. |
| `overtime_hours` | REVIEW_REQUIRED | 68.68 | 68.68 | 68.68 | p4_l65, p4_l66 | Nearest amount candidate to label 'שעות נוספות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `travel_reimbursement` | REVIEW_REQUIRED | 323.00 | 323.0 | 323.00 | p4_l58, p4_l59 | Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `income_tax` | REVIEW_REQUIRED | 10,000.00 | 10000.0 | 10,000.00 | p4_l50, p4_l49 | Nearest amount candidate to label 'מס הכנסה 20% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 398.00 | 398.0 | 398.00 | p4_l55, p4_l54 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 484.00 | 484.0 | 484.00 | p4_l60, p4_l61 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 68.68 | 68.68 | 68.68 | p4_l65, p4_l67 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | שעות נוספות; גילום | — | שעות נוספות; גילום | p4_l66, p4_l44 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6/26
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
התחלת עבודה
6 ותק-שנים:
"(0
יעקב ישראל סבירסקי
ת"ז
22****96
210.00
182.00
ועות עבודה
מתוך:
מחלקה:
22.00
22.00
וימי עבודה
מתוך:
100.00
54.95
היקף משרה %
תע' שעה:
דרגה:
ק/סניף:
דרוג :
חשבון:
|מינימום לחודש:
לשעה:
6,443.85
35.41
משרה:
משרה חודשי
```

</details>

## `valid_payslips_valid_2026_06_multi_p05`

- **Proposed employee key:** `emp_nid_94329fe7354f`
- **Source file:** `valid/payslips_valid_2026_06_multi.pdf`
- **Source page:** 5
- **Fixture intent:** `valid` (intent only — not a validation result)
- **OCR confidence:** 0.8650310559006211
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | שמולבי\ יהודה | — | שמולבי\ יהודה | p5_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). OCR contains unusual characters. |
| `national_id` | REVIEW_REQUIRED | 31****83 | 31****83 | 31****83 | p5_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p5_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6/26 | 6 | 6/26 | p5_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `payroll_year` | REVIEW_REQUIRED | 6/26 | 2026 | 6/26 | p5_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `base_salary` | REVIEW_REQUIRED | 100,000.00 | 100000.0 | 100,000.00 | p5_l52, p5_l54 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 100,323.00 | 100323.0 | 100,323.00 | p5_l84, p5_l83 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p5_l114, p5_l116 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | REVIEW_REQUIRED | 182.00 | 182.0 | 182.00 | p5_l21, p5_l22 | Hours candidate near label; verify against PDF (OCR often swaps columns). |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | REVIEW_REQUIRED | 323.00 | 323.0 | 323.00 | p5_l59, p5_l60 | Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `income_tax` | REVIEW_REQUIRED | 47,125.35 | 47125.35 | 47,125.35 | p5_l49, p5_l50 | Nearest amount candidate to label 'מס הכנסה 50% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 3,175.00 | 3175.0 | 3,175.00 | p5_l56, p5_l55 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 3,490.00 | 3490.0 | 3,490.00 | p5_l62, p5_l63 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 6,321.60 | 6321.6 | 6,321.60 | p5_l71, p5_l72 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | גילום | — | גילום | p5_l44 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6/26
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
ana תיק‎
טלפון:
פקס :
מס' עובד:
|התחלת עבודה
6 ותק-שנים:
"(0
שמולבי\ יהודה
ת"ז
31****83
182.00
182.00
ועות עבודה
מתוך:
מחלקה:
22.00
22.00
וימי עבודה
מתוך:
100.00
549.45
היקף משרה %
תע' שעה:
דרגה:
ק/סניף:
דרוג :
חשבון:
|מינימום לחודש:
לשעה:
6,443.85
35.41
משרה:
משרה חודשית
ת
```

</details>

## `valid_payslips_valid_2026_06_multi_p06`

- **Proposed employee key:** `emp_nid_fd0509db7499`
- **Source file:** `valid/payslips_valid_2026_06_multi.pdf`
- **Source page:** 6
- **Fixture intent:** `valid` (intent only — not a validation result)
- **OCR confidence:** 0.8674729241877256
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | יעל ויטלין | — | יעל ויטלין | p6_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 15****52 | 15****52 | 15****52 | p6_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p6_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6/26 | 6 | 6/26 | p6_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `payroll_year` | REVIEW_REQUIRED | 6/26 | 2026 | 6/26 | p6_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `base_salary` | REVIEW_REQUIRED | 2,200.00 | 2200.0 | 2,200.00 | p6_l52, p6_l55 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 2,200.00 | 2200.0 | 2,200.00 | p6_l67, p6_l66 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p6_l94, p6_l96 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | REVIEW_REQUIRED | 44.00 | 44.0 | 44.00 | p6_l21, p6_l22 | Hours candidate near label; verify against PDF (OCR often swaps columns). |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | MISSING | — | — | — | — | Label(s) ['נסיעות'] not found in OCR. |
| `income_tax` | REVIEW_REQUIRED | 2,200.00 | 2200.0 | 2,200.00 | p6_l52, p6_l51 | Nearest amount candidate to label 'מס הכנסה 10% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 16.00 | 16.0 | 16.00 | p6_l57, p6_l56 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 71.00 | 71.0 | 71.00 | p6_l58, p6_l59 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 71.00 | 71.0 | 71.00 | p6_l58, p6_l60 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | גילום | — | גילום | p6_l46 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6/26
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
התחלת עבודה
6 ותק-שנים:
"(0
יעל ויטלין
ת"ז
15****52
44.00
44.00
ועות עבודה
מתוך:
מחלקה:
22.00
22.00
וימי עבודה
מתוך:
100.00
50.00
היקף משרה %
תע' שעה:
דרגה:
ירושלים
100
ק/סניף:
דרוג :
חשבון:
טבריה
חודשי לפי שעות |מינימום לחודש:
לשעה:
6,443.85
```

</details>

## `valid_payslips_valid_2026_06_multi_p07`

- **Proposed employee key:** `emp_nid_9462ed1ce6ec`
- **Source file:** `valid/payslips_valid_2026_06_multi.pdf`
- **Source page:** 7
- **Fixture intent:** `valid` (intent only — not a validation result)
- **OCR confidence:** 0.8662007168458782
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | רחל בנימלני | — | רחל בנימלני | p7_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 56****34 | 56****34 | 56****34 | p7_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p7_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6/26 | 6 | 6/26 | p7_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `payroll_year` | REVIEW_REQUIRED | 6/26 | 2026 | 6/26 | p7_l1 | Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence). |
| `base_salary` | REVIEW_REQUIRED | 10,000.00 | 10000.0 | 10,000.00 | p7_l51, p7_l53 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 10,000.00 | 10000.0 | 10,000.00 | p7_l70, p7_l69 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p7_l97, p7_l99 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | CONFLICTING | 182.00 | 182.0 | 182.00@p7_l21; 165.00@p7_l20; 20.00@p7_l25; 22.00@p7_l26 | p7_l21, p7_l20, p7_l25, p7_l26, p7_l22 | Multiple hour-like numbers near hours label — confirm which is reported vs base. |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | MISSING | — | — | — | — | Label(s) ['נסיעות'] not found in OCR. |
| `income_tax` | REVIEW_REQUIRED | 10,000.00 | 10000.0 | 10,000.00 | p7_l50, p7_l49 | Nearest amount candidate to label 'מס הכנסה 14% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 241.00 | 241.0 | 241.00 | p7_l55, p7_l54 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 368.00 | 368.0 | 368.00 | p7_l61, p7_l62 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 368.00 | 368.0 | 368.00 | p7_l61, p7_l63 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | גילום | — | גילום | p7_l44 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6/26
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
התחלת עבודה
6 ותק-שנים:
"(0
רחל בנימלני
ת"ז
56****34
165.00
182.00
ועות עבודה
מתוך:
מחלקה:
20.00
22.00
וימי עבודה
מתוך:
100.00
54.95
היקף משרה %
תע' שעה:
דרגה:
ק/סניף:
דרוג :
חשבון:
|מינימום לחודש:
לשעה:
6,443.85
35.41
משרה:
משרה חודשית
תיאור
```

</details>

## `invalid_payslips_invalid_2026_07_multi_p01`

- **Proposed employee key:** `emp_nid_d7c0b66f9cea`
- **Source file:** `invalid/payslips_invalid_2026_07_multi.pdf`
- **Source page:** 1
- **Fixture intent:** `invalid` (intent only — not a validation result)
- **OCR confidence:** 0.8713058419243986
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | סבירסקי אורית | — | סבירסקי אורית | p1_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 30****19 | 30****19 | 30****19 | p1_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p1_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6 | 6 | 6 | p1_l1 | Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value. |
| `payroll_year` | REVIEW_REQUIRED | — | — | — | — | Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill. |
| `base_salary` | REVIEW_REQUIRED | 8,000.00 | 8000.0 | 8,000.00 | p1_l56, p1_l58 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 8,150.00 | 8150.0 | 8,150.00 | p1_l75, p1_l74 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p1_l100, p1_l102 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | CONFLICTING | 182.00 | 182.0 | 182.00@p1_l21; 250.00@p1_l20; 31.00@p1_l25; 22.00@p1_l26 | p1_l21, p1_l20, p1_l25, p1_l26, p1_l22 | Multiple hour-like numbers near hours label — confirm which is reported vs base. |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | REVIEW_REQUIRED | 15.00 | 15.0 | 15.00 | p1_l64, p1_l65 | Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `income_tax` | REVIEW_REQUIRED | 8,000.00 | 8000.0 | 8,000.00 | p1_l55, p1_l54 | Nearest amount candidate to label 'מס הכנסה 14% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 111.00 | 111.0 | 111.00 | p1_l60, p1_l59 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 272.00 | 272.0 | 272.00 | p1_l66, p1_l67 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 272.00 | 272.0 | 272.00 | p1_l66, p1_l68 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | גילום | — | גילום | p1_l49 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
התחלת עבודה
6 ותק-שנים:
"(78
סבירסקי אורית
ת"ז
30****19
250.00
182.00
ועות עבודה:
מתוך:
מחלקה:
31.00
22.00
4חשבות שכר
ימי עבודה:
מתוך:
100.00
43.96
היקף משרה %
תע' שעה:
דרגה:
הלל
2 (דירה 3)
ק/סניף:
רוג':
חשבון:
אלעד
4080234
|מינימום לחודש:
לשעה:
```

</details>

## `invalid_payslips_invalid_2026_07_multi_p02`

- **Proposed employee key:** `emp_nid_21a7b7d1eead`
- **Source file:** `invalid/payslips_invalid_2026_07_multi.pdf`
- **Source page:** 2
- **Fixture intent:** `invalid` (intent only — not a validation result)
- **OCR confidence:** 0.8692465753424657
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | סבירסקי יונה לב | — | סבירסקי יונה לב | p2_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 31****98 | 31****98 | 31****98 | p2_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p2_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6 | 6 | 6 | p2_l1 | Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value. |
| `payroll_year` | REVIEW_REQUIRED | — | — | — | — | Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill. |
| `base_salary` | REVIEW_REQUIRED | 15,000.00 | 15000.0 | 15,000.00 | p2_l57, p2_l59 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 17,886.80 | 17886.8 | 17,886.80 | p2_l76, p2_l75 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p2_l103, p2_l105 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | CONFLICTING | 182.00 | 182.0 | 182.00@p2_l21; 20000@p2_l20; 5.00@p2_l25; 22.00@p2_l26 | p2_l21, p2_l20, p2_l25, p2_l26, p2_l22 | Multiple hour-like numbers near hours label — confirm which is reported vs base. |
| `overtime_hours` | REVIEW_REQUIRED | 103.10 | 103.1 | 103.10 | p2_l65, p2_l66 | Nearest amount candidate to label 'שעות נוספות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `travel_reimbursement` | MISSING | — | — | — | — | Label(s) ['נסיעות'] not found in OCR. |
| `income_tax` | REVIEW_REQUIRED | 1,185.21 | 1185.21 | 1,185.21 | p2_l54, p2_l55 | Nearest amount candidate to label 'מס הכנסה 20% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 793.00 | 793.0 | 793.00 | p2_l61, p2_l60 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 775.00 | 775.0 | 775.00 | p2_l67, p2_l68 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 775.00 | 775.0 | 775.00 | p2_l67, p2_l69 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | שעות נוספות; גילום | — | שעות נוספות; גילום | p2_l66, p2_l49 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
התחלת עבודה
6 ותק-שנים:
"(78
סבירסקי יונה לב
ת"ז
31****98
20000
182.00
ועות עבודה:
מתוך:
מחלקה:
5.00
22.00
1-עורכי דין
ימי עבודה:
מתוך:
100.00
82.42
היקף משרה %
תע' שעה:
דרגה:
הלל
2 (דירה 3)
ק/סניף:
רוג':
חשבון:
אלעד
4080234
|מינימום לחודש:
לשעה
```

</details>

## `invalid_payslips_invalid_2026_07_multi_p03`

- **Proposed employee key:** `emp_nid_5d945bcea62c`
- **Source file:** `invalid/payslips_invalid_2026_07_multi.pdf`
- **Source page:** 3
- **Fixture intent:** `invalid` (intent only — not a validation result)
- **OCR confidence:** 0.8688686131386861
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | אביגיל תמר סבירסקי | — | אביגיל תמר סבירסקי | p3_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 33****46 | 33****46 | 33****46 | p3_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p3_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6 | 6 | 6 | p3_l1 | Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value. |
| `payroll_year` | REVIEW_REQUIRED | — | — | — | — | Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill. |
| `base_salary` | REVIEW_REQUIRED | 2,000.00 | 2000.0 | 2,000.00 | p3_l54, p3_l57 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 2,000.00 | 2000.0 | 2,000.00 | p3_l67, p3_l66 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p3_l94, p3_l96 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | CONFLICTING | 182.00 | 182.0 | 182.00@p3_l21; 100.00@p3_l20; 5.00@p3_l25; 22.00@p3_l26 | p3_l21, p3_l20, p3_l25, p3_l26, p3_l22 | Multiple hour-like numbers near hours label — confirm which is reported vs base. |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | MISSING | — | — | — | — | Label(s) ['נסיעות'] not found in OCR. |
| `income_tax` | REVIEW_REQUIRED | 2,000.00 | 2000.0 | 2,000.00 | p3_l54, p3_l53 | Nearest amount candidate to label 'מס הכנסה 10% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p3_l56, p3_l58 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p3_l56, p3_l59 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 120.00 | 120.0 | 120.00 | p3_l63, p3_l60 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | גילום | — | גילום | p3_l48 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
Nanna}‏ עבודה:
6 ותק-שנים:
"(78
אביגיל תמר סבירסקי
ת"ז
33****46
100.00
182.00
ועות עבודה:
מתוך:
מחלקה:
5.00
22.00
anv-3‏ התמחות
ימי עבודה:
מתוך:
2000
היקף משרה %
תע' שעה:
דרגה:
הלל
32
ק/סניף:
דרוג :
חשבון:
אלעד
408
|מינימום לחודש:
לשעה:
לפי שעות
```

</details>

## `invalid_payslips_invalid_2026_07_multi_p04`

- **Proposed employee key:** `emp_nid_17f2d60c389c`
- **Source file:** `invalid/payslips_invalid_2026_07_multi.pdf`
- **Source page:** 4
- **Fixture intent:** `invalid` (intent only — not a validation result)
- **OCR confidence:** 0.8725874125874126
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | יעקב ישראל סבירסקי | — | יעקב ישראל סבירסקי | p4_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 22****96 | 22****96 | 22****96 | p4_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p4_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6 | 6 | 6 | p4_l1 | Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value. |
| `payroll_year` | REVIEW_REQUIRED | — | — | — | — | Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill. |
| `base_salary` | REVIEW_REQUIRED | 10,000.00 | 10000.0 | 10,000.00 | p4_l52, p4_l54 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 10,323.00 | 10323.0 | 10,323.00 | p4_l72, p4_l71 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p4_l102, p4_l104 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | CONFLICTING | 182.00 | 182.0 | 182.00@p4_l21; 210.00@p4_l20; 22.00@p4_l25; 22.00@p4_l26 | p4_l21, p4_l20, p4_l25, p4_l26, p4_l22 | Multiple hour-like numbers near hours label — confirm which is reported vs base. |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | REVIEW_REQUIRED | 323.00 | 323.0 | 323.00 | p4_l59, p4_l60 | Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `income_tax` | REVIEW_REQUIRED | 10,000.00 | 10000.0 | 10,000.00 | p4_l51, p4_l50 | Nearest amount candidate to label 'מס הכנסה 20% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 264.00 | 264.0 | 264.00 | p4_l56, p4_l55 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 384.00 | 384.0 | 384.00 | p4_l61, p4_l62 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 384.00 | 384.0 | 384.00 | p4_l61, p4_l63 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | גילום | — | גילום | p4_l45 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
התחלת עבודה
6 ותק-שנים:
"(78
יעקב ישראל סבירסקי
ת"ז
22****96
210.00
182.00
ועות עבודה:
מתוך:
מחלקה:
22.00
22.00
anv-3‏ התמחות
ימי עבודה:
מתוך:
100.00
54.95
היקף משרה %
תע' שעה:
דרגה:
ק/סניף:
דרוג :
חשבון:
|מינימום לחודש:
לשעה:
6,443.85
35.41
משר
```

</details>

## `invalid_payslips_invalid_2026_07_multi_p05`

- **Proposed employee key:** `emp_nid_94329fe7354f`
- **Source file:** `invalid/payslips_invalid_2026_07_multi.pdf`
- **Source page:** 5
- **Fixture intent:** `invalid` (intent only — not a validation result)
- **OCR confidence:** 0.8623582089552239
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | שמולבי\ יהודה | — | שמולבי\ יהודה | p5_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). OCR contains unusual characters. |
| `national_id` | REVIEW_REQUIRED | 31****83 | 31****83 | 31****83 | p5_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p5_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6 | 6 | 6 | p5_l1 | Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value. |
| `payroll_year` | REVIEW_REQUIRED | — | — | — | — | Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill. |
| `base_salary` | REVIEW_REQUIRED | 100,000.00 | 100000.0 | 100,000.00 | p5_l54, p5_l55 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 101,199.00 | 101199.0 | 101,199.00 | p5_l90, p5_l89 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | MISSING | — | — | — | — | Label(s) ['שכר נטו', 'נטו לתשלום', 'לתשלום נטו', 'סה"כ נטו', 'נטו:', 'נטו '] not found in OCR. |
| `regular_hours` | REVIEW_REQUIRED | 182.00 | 182.0 | 182.00 | p5_l21, p5_l22 | Hours candidate near label; verify against PDF (OCR often swaps columns). |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | REVIEW_REQUIRED | 323.00 | 323.0 | 323.00 | p5_l60, p5_l61 | Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `income_tax` | REVIEW_REQUIRED | 47,563.35 | 47563.35 | 47,563.35 | p5_l50, p5_l51 | Nearest amount candidate to label 'מס הכנסה 50% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 3,175.00 | 3175.0 | 3,175.00 | p5_l57, p5_l56 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 2,534.00 | 2534.0 | 2,534.00 | p5_l62, p5_l63 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 3,918.28 | 3918.28 | 3,918.28 | p5_l74, p5_l75 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | גילום | — | גילום | p5_l45 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
התחלת עבודה
6 ותק-שנים:
"(78
שמולבי\ יהודה
ת"ז
31****83
182.00
182.00
ועות עבודה:
מתוך:
מחלקה:
22.00
22.00
1-עורכי דין
ימי עבודה:
מתוך:
100.00
549.45
היקף משרה %
תע' שעה:
דרגה:
ק/סניף:
דרוג :
חשבון:
|מינימום לחודש:
לשעה:
6,443.85
35.41
משרה:
משר
```

</details>

## `invalid_payslips_invalid_2026_07_multi_p06`

- **Proposed employee key:** `emp_nid_fd0509db7499`
- **Source file:** `invalid/payslips_invalid_2026_07_multi.pdf`
- **Source page:** 6
- **Fixture intent:** `invalid` (intent only — not a validation result)
- **OCR confidence:** 0.8776041666666666
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | יעל ויטלין | — | יעל ויטלין | p6_l16 | Name candidate from line before ID token (no ת"ז line). |
| `national_id` | REVIEW_REQUIRED | 15****52 | 15****52 | 15****52 | p6_l17 | Hyphenated ID-like token without clear ת"ז adjacency. Confirm on PDF. |
| `employee_number` | MISSING | — | — | מס' עובד: | p6_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6 | 6 | 6 | p6_l1 | Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value. |
| `payroll_year` | REVIEW_REQUIRED | — | — | — | — | Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill. |
| `base_salary` | MISSING | — | — | — | — | Label(s) ['שכר יסוד'] not found in OCR. |
| `gross_salary` | REVIEW_REQUIRED | 2,200.00 | 2200.0 | 2,200.00 | p6_l40, p6_l39 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 1,893.00 | 1893.0 | 1,893.00 | p6_l52, p6_l51 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | REVIEW_REQUIRED | ועות עבודה: | — | ועות עבודה: | p6_l18 | Hours label present; numeric hours not uniquely identified. |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | MISSING | — | — | — | — | Label(s) ['נסיעות'] not found in OCR. |
| `income_tax` | REVIEW_REQUIRED | 2,200.00 | 2200.0 | 2,200.00 | p6_l32, p6_l31 | Nearest amount candidate to label 'מס הכנסה 10% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p6_l33, p6_l34 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p6_l33, p6_l35 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p6_l33, p6_l36 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | MISSING | — | — | — | — | No additional earning labels clearly identified beyond base/travel/OT exploration. |
| `other_deductions` | REVIEW_REQUIRED | ניכוי רשות; ניכויי חובה וגמל | — | ניכוי רשות; ניכויי חובה וגמל | p6_l37, p6_l42 | Additional deduction labels present; confirm amounts from PDF. |

<details><summary>OCR text preview</summary>

```
6
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
6 ותק-שנים:
"(78
יעל ויטלין
15****52
ועות עבודה:
6ניהול משרד
ימי עבודה:
היקף משרה %
ירושלים
ק/סניף:
טבריה
|מינימום לחודש:
חודשי לפי שעות
6,443.85
ניכויים למס
שווי למס
סכום לתשלום
מס הכנסה 10% שולי
2,200.00
0.00
ביטוח לאומי
מס בריאות
ניכוי לגמל
נ
```

</details>

## `invalid_payslips_invalid_2026_07_multi_p07`

- **Proposed employee key:** `emp_nid_9462ed1ce6ec`
- **Source file:** `invalid/payslips_invalid_2026_07_multi.pdf`
- **Source page:** 7
- **Fixture intent:** `invalid` (intent only — not a validation result)
- **OCR confidence:** 0.8665591397849463
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. Evidence IDs from OCR layout lines (p{page}_l{n}).

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | REVIEW_REQUIRED | רחל בנימלני | — | רחל בנימלני | p7_l17 | Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). |
| `national_id` | REVIEW_REQUIRED | 56****34 | 56****34 | 56****34 | p7_l19 | National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed. |
| `employee_number` | MISSING | — | — | מס' עובד: | p7_l13 | Employee-number label present; no value clearly OCR'd beside it. |
| `payroll_month` | REVIEW_REQUIRED | 6 | 6 | 6 | p7_l1 | Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value. |
| `payroll_year` | REVIEW_REQUIRED | — | — | — | — | Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill. |
| `base_salary` | REVIEW_REQUIRED | 10,000.00 | 10000.0 | 10,000.00 | p7_l52, p7_l54 | Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `gross_salary` | REVIEW_REQUIRED | 13,000.00 | 13000.0 | 13,000.00 | p7_l70, p7_l69 | Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `net_salary` | REVIEW_REQUIRED | 0.00 | 0.0 | 0.00 | p7_l97, p7_l99 | Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `regular_hours` | REVIEW_REQUIRED | 182.00 | 182.0 | 182.00 | p7_l21, p7_l22 | Hours candidate near label; verify against PDF (OCR often swaps columns). |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | MISSING | — | — | — | — | Label(s) ['נסיעות'] not found in OCR. |
| `income_tax` | REVIEW_REQUIRED | 10,000.00 | 10000.0 | 10,000.00 | p7_l51, p7_l50 | Nearest amount candidate to label 'מס הכנסה 20% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `national_insurance` | REVIEW_REQUIRED | 451.00 | 451.0 | 451.00 | p7_l56, p7_l55 | Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `health_insurance` | REVIEW_REQUIRED | 523.00 | 523.0 | 523.00 | p7_l61, p7_l62 | Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `pension_deductions` | REVIEW_REQUIRED | 523.00 | 523.0 | 523.00 | p7_l61, p7_l63 | Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval. |
| `other_earnings` | REVIEW_REQUIRED | גילום | — | גילום | p7_l45 | Additional earning-related labels present; extract specific amounts from PDF columns (not auto-summed). |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
6
תלוש משכורת
תאריך הדפסה 08/07/26
PAYROLCOPYLOT
תיק נ. ב"ל
93511111100
935111111
תיק ניכויים
הדגמה בלבד 32 אלעד 4080234
תיק במ"ה
טלפון:
פקס :
מס' עובד:
התחלת עבודה
6 ותק-שנים:
"(78
רחל בנימלני
ת"ז
56****34
182.00
182.00
ועות עבודה:
מתוך:
מחלקה:
22.00
22.00
2-מתמחים
ימי עבודה:
מתוך:
100.00
54.95
היקף משרה %
תע' שעה:
דרגה:
ק/סניף:
דרוג :
חשבון:
|מינימום לחודש:
לשעה:
6,443.85
35.41
משרה:
משרה חודש
```

</details>

## `valid_payslip_valid_2026_06_employee_001_p01`

- **Proposed employee key:** `emp_ungrouped_valid_payslip_valid_2026_06_employee_001_p01`
- **Source file:** `valid/payslip_valid_2026_06_employee_001.png`
- **Source page:** 1
- **Fixture intent:** `valid` (intent only — not a validation result)
- **OCR confidence:** 0.6542592592592592
- **Page review status:** `REVIEW_REQUIRED`
- **Notes:** Parser values intentionally ignored. All monetary/identity fields need human PDF confirmation. No word/line geometry for this source in stored layout OCR; evidence_ids are synthetic sequential from text lines only and must be re-verified.

| Field | Status | OCR raw | Normalized candidate | Source text | Evidence IDs | Reviewer notes |
|---|---|---|---|---|---|---|
| `employee_name` | UNREADABLE | — | — | תלוש משכורת 6/26 תאריך הדפסה 08/07/26 PAYROLCOPYLOT 4000234 הדגמה בלבד 32 אלעד‎ eT - seta 32 דירת 3( 4080234 8,000.00 323.00 54.93 ‘na הפקדות מעסיק לקופות‎ 8,872.30 a a \| הו \| =- 0 00 0.00) ewew ויוי  | — | PNG OCR too weak for reliable identity/period. Prefer matching PDF page for seed review. |
| `national_id` | UNREADABLE | — | — | 62****00 | — | PNG OCR too weak for reliable identity/period. Prefer matching PDF page for seed review. |
| `employee_number` | UNREADABLE | — | — | תלוש משכורת 6/26 תאריך הדפסה 08/07/26 PAYROLCOPYLOT 4000234 הדגמה בלבד 32 אלעד‎ eT - seta 32 דירת 3( 4080234 8,000.00 323.00 54.93 ‘na הפקדות מעסיק לקופות‎ 8,872.30 a a \| הו \| =- 0 00 0.00) ewew ויוי  | — | PNG OCR too weak for reliable identity/period. Prefer matching PDF page for seed review. |
| `payroll_month` | UNREADABLE | — | — | תלוש משכורת 6/26 תאריך הדפסה 08/07/26 PAYROLCOPYLOT 4000234 הדגמה בלבד 32 אלעד‎ eT - seta 32 דירת 3( 4080234 8,000.00 323.00 54.93 ‘na הפקדות מעסיק לקופות‎ 8,872.30 a a \| הו \| =- 0 00 0.00) ewew ויוי  | — | PNG OCR too weak for reliable identity/period. Prefer matching PDF page for seed review. |
| `payroll_year` | UNREADABLE | — | — | תלוש משכורת 6/26 תאריך הדפסה 08/07/26 PAYROLCOPYLOT 4000234 הדגמה בלבד 32 אלעד‎ eT - seta 32 דירת 3( 4080234 8,000.00 323.00 54.93 ‘na הפקדות מעסיק לקופות‎ 8,872.30 a a \| הו \| =- 0 00 0.00) ewew ויוי  | — | PNG OCR too weak for reliable identity/period. Prefer matching PDF page for seed review. |
| `base_salary` | REVIEW_REQUIRED | 8,000.00 | 8000.0 | 8,000.00, 323.00, 54.93, 8,872.30, 0.00, 450.00 | — | PNG shows amounts without reliable labels/name/ID. Cross-check against recommended PDF page; do not seed from PNG alone. |
| `gross_salary` | MISSING | — | — | — | — | Label(s) ['סה"כ תשלומים', 'סה״כ תשלומים', 'סהכ תשלומים'] not found in OCR. |
| `net_salary` | MISSING | — | — | — | — | Label(s) ['שכר נטו', 'נטו לתשלום', 'לתשלום נטו', 'סה"כ נטו', 'נטו:', 'נטו '] not found in OCR. |
| `regular_hours` | MISSING | — | — | — | — | Hours label(s) ['שעות עבודה', 'ועות עבודה'] not found. |
| `overtime_hours` | MISSING | — | — | — | — | Label(s) ['שעות נוספות'] not found in OCR. |
| `travel_reimbursement` | CONFLICTING | 323.00 | 323.0 | 8,000.00, 323.00, 54.93, 8,872.30, 0.00, 450.00 | — | Unlabeled amount sequence on PNG; column meaning uncertain. |
| `income_tax` | MISSING | — | — | — | — | Label(s) ['מס הכנסה'] not found in OCR. |
| `national_insurance` | MISSING | — | — | — | — | Label(s) ['ביטוח לאומי'] not found in OCR. |
| `health_insurance` | MISSING | — | — | — | — | Label(s) ['מס בריאות'] not found in OCR. |
| `pension_deductions` | MISSING | — | — | — | — | Label(s) ['ניכוי לגמל', 'אלשולר'] not found in OCR. |
| `other_earnings` | MISSING | — | — | — | — | No additional earning labels clearly identified beyond base/travel/OT exploration. |
| `other_deductions` | MISSING | — | — | — | — | No extra deduction labels clearly identified beyond tax/NI/health/pension exploration. |

<details><summary>OCR text preview</summary>

```
תלוש משכורת 6/26 תאריך הדפסה 08/07/26
PAYROLCOPYLOT
4000234 הדגמה בלבד 32 אלעד‎
eT - seta
32 דירת 3(
4080234
8,000.00
323.00
54.93
‘na הפקדות מעסיק לקופות‎
8,872.30
a a |
הו |
=-
0 00 0.00) ewew
ויוי )450.00
תלושים להדמיה INIT‏
הופק ע"י: לוט" ושות' rea Ty‏ "משכרת טר" טל שקץ משרכת MA‏
```

</details>

## Edit checklist (copy into reviewer notes)

- [ ] All national IDs confirmed against PDF
- [ ] Employee merges only by confirmed identical ID
- [ ] Period month/year confirmed (fixture path is not authority)
- [ ] Base / gross / net / deductions confirmed from correct columns
- [ ] PNG page deferred in favor of PDF match if used
- [ ] Explicit approval recorded before any seed generation
