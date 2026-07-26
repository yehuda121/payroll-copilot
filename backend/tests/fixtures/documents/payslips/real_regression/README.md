# Real payslip regression harness (semantic_v1)

Place anonymized real-payslip fixtures here when an approved fixture policy allows it.

## Expected layout

```
backend/tests/fixtures/documents/payslips/real_regression/
  README.md                 (this file)
  manifests/
    case_01.json            (expected canonical fields; no PII in git if possible)
  documents/                (gitignored unless anonymized + approved)
    case_01.pdf
```

## Manifest schema (example)

```json
{
  "id": "case_01",
  "document": "documents/case_01.pdf",
  "language": "he",
  "expected": {
    "employee_name": {"present": true, "equals": null},
    "national_id": {"present": true},
    "pay_period": {"present": true},
    "gross_salary": {"present": true},
    "net_salary": {"present": true},
    "must_not_map_to_canonical": ["דמי הבראה"]
  },
  "notes": "Unlabeled header name must resolve to employee_name"
}
```

## Status

The ~7 real payslips observed during the extraction audit were **not** found as
committed fixtures in this repository. Do not fabricate pass claims.

Add fixtures later and wire `test_payslip_semantic_real_regression.py` (skipped
until documents exist).
