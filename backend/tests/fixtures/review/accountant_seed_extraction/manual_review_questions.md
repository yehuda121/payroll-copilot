# Manual review questions (seed approval)

> Answer before approving any final seed. Do not invent values.

## Cross-cutting

1. Confirm that **parser/LLM values will not be used** for seed fields.
2. Confirm national IDs in `seed_approval_table.json` match the printed PDF (Markdown is masked).
3. Confirm employees are merged **only** when national ID digits match exactly after your confirmation.
4. For invalid-fixture July slips: confirm month/year from the **printed** slip (OCR often shows month `6` without year).
5. Confirm whether PNG `payslip_valid_2026_06_employee_001.png` should be excluded from seed in favor of the matching PDF page.

## Per proposed employee group

### `emp_nid_d7c0b66f9cea`

- Masked ID: `30****19`
- Payslips: valid_payslips_valid_2026_06_multi_p01, invalid_payslips_invalid_2026_07_multi_p01
- OCR names observed: ['סבירסקי אורית']
- [ ] Is the national ID correct on every listed page?
- [ ] Are OCR name variants the same person (do **not** merge on name alone if IDs differ)?
- [ ] Approve this employee key for future seed? (yes/no)

### `emp_nid_21a7b7d1eead`

- Masked ID: `31****98`
- Payslips: valid_payslips_valid_2026_06_multi_p02, invalid_payslips_invalid_2026_07_multi_p02
- OCR names observed: ['סבירסקי יונה לב']
- [ ] Is the national ID correct on every listed page?
- [ ] Are OCR name variants the same person (do **not** merge on name alone if IDs differ)?
- [ ] Approve this employee key for future seed? (yes/no)

### `emp_nid_5d945bcea62c`

- Masked ID: `33****46`
- Payslips: valid_payslips_valid_2026_06_multi_p03, invalid_payslips_invalid_2026_07_multi_p03
- OCR names observed: ['אביגיל תמר סבירסקי']
- [ ] Is the national ID correct on every listed page?
- [ ] Are OCR name variants the same person (do **not** merge on name alone if IDs differ)?
- [ ] Approve this employee key for future seed? (yes/no)

### `emp_nid_17f2d60c389c`

- Masked ID: `22****96`
- Payslips: valid_payslips_valid_2026_06_multi_p04, invalid_payslips_invalid_2026_07_multi_p04
- OCR names observed: ['יעקב ישראל סבירסקי']
- [ ] Is the national ID correct on every listed page?
- [ ] Are OCR name variants the same person (do **not** merge on name alone if IDs differ)?
- [ ] Approve this employee key for future seed? (yes/no)

### `emp_nid_94329fe7354f`

- Masked ID: `31****83`
- Payslips: valid_payslips_valid_2026_06_multi_p05, invalid_payslips_invalid_2026_07_multi_p05
- OCR names observed: ['שמולבי\\ יהודה']
- [ ] Is the national ID correct on every listed page?
- [ ] Are OCR name variants the same person (do **not** merge on name alone if IDs differ)?
- [ ] Approve this employee key for future seed? (yes/no)

### `emp_nid_fd0509db7499`

- Masked ID: `15****52`
- Payslips: valid_payslips_valid_2026_06_multi_p06, invalid_payslips_invalid_2026_07_multi_p06
- OCR names observed: ['יעל ויטלין']
- [ ] Is the national ID correct on every listed page?
- [ ] Are OCR name variants the same person (do **not** merge on name alone if IDs differ)?
- [ ] Approve this employee key for future seed? (yes/no)

### `emp_nid_9462ed1ce6ec`

- Masked ID: `56****34`
- Payslips: valid_payslips_valid_2026_06_multi_p07, invalid_payslips_invalid_2026_07_multi_p07
- OCR names observed: ['רחל בנימלני']
- [ ] Is the national ID correct on every listed page?
- [ ] Are OCR name variants the same person (do **not** merge on name alone if IDs differ)?
- [ ] Approve this employee key for future seed? (yes/no)

### `emp_ungrouped_valid_payslip_valid_2026_06_employee_001_p01`

- Masked ID: `None`
- Payslips: valid_payslip_valid_2026_06_employee_001_p01
- OCR names observed: []
- [ ] Is the national ID correct on every listed page?
- [ ] Are OCR name variants the same person (do **not** merge on name alone if IDs differ)?
- [ ] Approve this employee key for future seed? (yes/no)

## Per page — critical field questions

### `valid_payslips_valid_2026_06_multi_p01` (file `valid/payslips_valid_2026_06_multi.pdf` p1)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`סבירסקי אורית` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`30****19` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `base_salary` status=`REVIEW_REQUIRED` OCR=`8,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`8,872.30` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`REVIEW_REQUIRED` OCR=`323.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`8,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 14% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`162.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`309.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`54.93` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.

### `valid_payslips_valid_2026_06_multi_p02` (file `valid/payslips_valid_2026_06_multi.pdf` p2)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`סבירסקי יונה לב` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`31****98` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `base_salary` status=`REVIEW_REQUIRED` OCR=`7,500.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`7,839.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`REVIEW_REQUIRED` OCR=`22.60` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`7,500.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 14% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`90.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`256.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`256.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.

### `valid_payslips_valid_2026_06_multi_p03` (file `valid/payslips_valid_2026_06_multi.pdf` p3)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`אביגיל תמר סבירסקי` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`33****46` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `base_salary` status=`REVIEW_REQUIRED` OCR=`6,442.80` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`6,765.80` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`REVIEW_REQUIRED` OCR=`323.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`6,442.80` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 10% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`323.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`323.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.

### `valid_payslips_valid_2026_06_multi_p04` (file `valid/payslips_valid_2026_06_multi.pdf` p4)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`יעקב ישראל סבירסקי` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`22****96` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `base_salary` status=`REVIEW_REQUIRED` OCR=`10,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`12,246.04` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`REVIEW_REQUIRED` OCR=`323.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`10,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 20% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`398.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`484.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`68.68` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- **Conflicts to resolve:** regular_hours

### `valid_payslips_valid_2026_06_multi_p05` (file `valid/payslips_valid_2026_06_multi.pdf` p5)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`שמולבי\ יהודה` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). OCR contains unusual characters.
- `national_id` status=`REVIEW_REQUIRED` OCR=`31****83` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `base_salary` status=`REVIEW_REQUIRED` OCR=`100,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`100,323.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`REVIEW_REQUIRED` OCR=`323.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`47,125.35` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 50% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`3,175.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`3,490.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`6,321.60` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.

### `valid_payslips_valid_2026_06_multi_p06` (file `valid/payslips_valid_2026_06_multi.pdf` p6)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`יעל ויטלין` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`15****52` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `base_salary` status=`REVIEW_REQUIRED` OCR=`2,200.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`2,200.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['נסיעות'] not found in OCR.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`2,200.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 10% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`16.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`71.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`71.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.

### `valid_payslips_valid_2026_06_multi_p07` (file `valid/payslips_valid_2026_06_multi.pdf` p7)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`רחל בנימלני` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`56****34` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`6/26` — confirm/correct/mark missing? Notes: Header token interpreted as MM/YY → month=6, year=2026. Confirm vs printed slip (fixture path suggests 6/2026 but is not evidence).
- `base_salary` status=`REVIEW_REQUIRED` OCR=`10,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`10,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['נסיעות'] not found in OCR.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`10,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 14% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`241.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`368.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`368.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- **Conflicts to resolve:** regular_hours

### `invalid_payslips_invalid_2026_07_multi_p01` (file `invalid/payslips_invalid_2026_07_multi.pdf` p1)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`סבירסקי אורית` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`30****19` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6` — confirm/correct/mark missing? Notes: Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value.
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`None` — confirm/correct/mark missing? Notes: Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill.
- `base_salary` status=`REVIEW_REQUIRED` OCR=`8,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`8,150.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`REVIEW_REQUIRED` OCR=`15.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`8,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 14% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`111.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`272.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`272.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- **Conflicts to resolve:** regular_hours

### `invalid_payslips_invalid_2026_07_multi_p02` (file `invalid/payslips_invalid_2026_07_multi.pdf` p2)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`סבירסקי יונה לב` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`31****98` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6` — confirm/correct/mark missing? Notes: Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value.
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`None` — confirm/correct/mark missing? Notes: Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill.
- `base_salary` status=`REVIEW_REQUIRED` OCR=`15,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`17,886.80` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['נסיעות'] not found in OCR.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`1,185.21` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 20% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`793.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`775.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`775.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- **Conflicts to resolve:** regular_hours

### `invalid_payslips_invalid_2026_07_multi_p03` (file `invalid/payslips_invalid_2026_07_multi.pdf` p3)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`אביגיל תמר סבירסקי` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`33****46` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6` — confirm/correct/mark missing? Notes: Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value.
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`None` — confirm/correct/mark missing? Notes: Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill.
- `base_salary` status=`REVIEW_REQUIRED` OCR=`2,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`2,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['נסיעות'] not found in OCR.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`2,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 10% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`120.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- **Conflicts to resolve:** regular_hours

### `invalid_payslips_invalid_2026_07_multi_p04` (file `invalid/payslips_invalid_2026_07_multi.pdf` p4)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`יעקב ישראל סבירסקי` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`22****96` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6` — confirm/correct/mark missing? Notes: Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value.
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`None` — confirm/correct/mark missing? Notes: Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill.
- `base_salary` status=`REVIEW_REQUIRED` OCR=`10,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`10,323.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`REVIEW_REQUIRED` OCR=`323.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`10,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 20% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`264.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`384.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`384.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- **Conflicts to resolve:** regular_hours

### `invalid_payslips_invalid_2026_07_multi_p05` (file `invalid/payslips_invalid_2026_07_multi.pdf` p5)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`שמולבי\ יהודה` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR). OCR contains unusual characters.
- `national_id` status=`REVIEW_REQUIRED` OCR=`31****83` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6` — confirm/correct/mark missing? Notes: Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value.
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`None` — confirm/correct/mark missing? Notes: Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill.
- `base_salary` status=`REVIEW_REQUIRED` OCR=`100,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`101,199.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['שכר נטו', 'נטו לתשלום', 'לתשלום נטו', 'סה"כ נטו', 'נטו:', 'נטו '] not found in OCR.
- `travel_reimbursement` status=`REVIEW_REQUIRED` OCR=`323.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נסיעות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`47,563.35` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 50% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`3,175.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`2,534.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`3,918.28` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.

### `invalid_payslips_invalid_2026_07_multi_p06` (file `invalid/payslips_invalid_2026_07_multi.pdf` p6)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`יעל ויטלין` — confirm/correct/mark missing? Notes: Name candidate from line before ID token (no ת"ז line).
- `national_id` status=`REVIEW_REQUIRED` OCR=`15****52` — confirm/correct/mark missing? Notes: Hyphenated ID-like token without clear ת"ז adjacency. Confirm on PDF.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6` — confirm/correct/mark missing? Notes: Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value.
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`None` — confirm/correct/mark missing? Notes: Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill.
- `base_salary` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['שכר יסוד'] not found in OCR.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`2,200.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`1,893.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['נסיעות'] not found in OCR.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`2,200.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 10% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.

### `invalid_payslips_invalid_2026_07_multi_p07` (file `invalid/payslips_invalid_2026_07_multi.pdf` p7)

- `employee_name` status=`REVIEW_REQUIRED` OCR=`רחל בנימלני` — confirm/correct/mark missing? Notes: Hebrew name candidate immediately above ת"ז. Confirm against source PDF (do not auto-fix OCR).
- `national_id` status=`REVIEW_REQUIRED` OCR=`56****34` — confirm/correct/mark missing? Notes: National ID candidate immediately below ת"ז. Digits-only normalize only when 8–9 digits. Must be human-confirmed before grouping/seed.
- `payroll_month` status=`REVIEW_REQUIRED` OCR=`6` — confirm/correct/mark missing? Notes: Only month-like header digit '6' found (no /YY). Year not on this OCR token. Fixture path suggests 2026-07 but is NOT used as value.
- `payroll_year` status=`REVIEW_REQUIRED` OCR=`None` — confirm/correct/mark missing? Notes: Year not printed next to month header in OCR. Fixture filename hints 2026 — human must confirm from source PDF, do not auto-fill.
- `base_salary` status=`REVIEW_REQUIRED` OCR=`10,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'שכר יסוד'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `gross_salary` status=`REVIEW_REQUIRED` OCR=`13,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'סה"כ תשלומים'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `net_salary` status=`REVIEW_REQUIRED` OCR=`0.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'נטו לתשלום'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `travel_reimbursement` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['נסיעות'] not found in OCR.
- `income_tax` status=`REVIEW_REQUIRED` OCR=`10,000.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס הכנסה 20% שולי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `national_insurance` status=`REVIEW_REQUIRED` OCR=`451.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ביטוח לאומי'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `health_insurance` status=`REVIEW_REQUIRED` OCR=`523.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'מס בריאות'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.
- `pension_deductions` status=`REVIEW_REQUIRED` OCR=`523.00` — confirm/correct/mark missing? Notes: Nearest amount candidate to label 'ניכוי לגמל'. Confirm column mapping (quantity/rate/taxable/payment) on PDF before seed approval.

### `valid_payslip_valid_2026_06_employee_001_p01` (file `valid/payslip_valid_2026_06_employee_001.png` p1)

- `employee_name` status=`UNREADABLE` OCR=`None` — confirm/correct/mark missing? Notes: PNG OCR too weak for reliable identity/period. Prefer matching PDF page for seed review.
- `national_id` status=`UNREADABLE` OCR=`None` — confirm/correct/mark missing? Notes: PNG OCR too weak for reliable identity/period. Prefer matching PDF page for seed review.
- `payroll_month` status=`UNREADABLE` OCR=`None` — confirm/correct/mark missing? Notes: PNG OCR too weak for reliable identity/period. Prefer matching PDF page for seed review.
- `payroll_year` status=`UNREADABLE` OCR=`None` — confirm/correct/mark missing? Notes: PNG OCR too weak for reliable identity/period. Prefer matching PDF page for seed review.
- `base_salary` status=`REVIEW_REQUIRED` OCR=`8,000.00` — confirm/correct/mark missing? Notes: PNG shows amounts without reliable labels/name/ID. Cross-check against recommended PDF page; do not seed from PNG alone.
- `gross_salary` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['סה"כ תשלומים', 'סה״כ תשלומים', 'סהכ תשלומים'] not found in OCR.
- `net_salary` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['שכר נטו', 'נטו לתשלום', 'לתשלום נטו', 'סה"כ נטו', 'נטו:', 'נטו '] not found in OCR.
- `travel_reimbursement` status=`CONFLICTING` OCR=`323.00` — confirm/correct/mark missing? Notes: Unlabeled amount sequence on PNG; column meaning uncertain.
- `income_tax` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['מס הכנסה'] not found in OCR.
- `national_insurance` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['ביטוח לאומי'] not found in OCR.
- `health_insurance` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['מס בריאות'] not found in OCR.
- `pension_deductions` status=`MISSING` OCR=`None` — confirm/correct/mark missing? Notes: Label(s) ['ניכוי לגמל', 'אלשולר'] not found in OCR.
- **Conflicts to resolve:** travel_reimbursement

## Sign-off

- Reviewer name:
- Date:
- Approved to generate final seed: **NO** / YES (circle)
- Blocking items remaining:
