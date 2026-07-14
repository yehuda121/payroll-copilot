# Accountant Fixture Extraction Review

> REVIEW ARTIFACTS ONLY — NOT APPROVED SEED DATA

## Executive Summary

- **Files processed:** 3
- **Pages processed:** 15
- **Payslips detected:** 15
- **Proposed employee groups:** 0
- **Ungrouped candidates:** 15
- **Confirmed fields:** 0
- **Uncertain fields:** 0
- **Missing fields:** 360
- **Requires human review:** 0
- **Conflicts:** 0
- **Failed pages:** 0
- **Pipeline warnings:** 75


## Parser quality note (blocking)

OCR completed successfully for all 15 pages (Tesseract). The payslip parser returned **all fields as MISSING** after semantic validation + one retry (`parser_semantic_retry_failed`) on every slip. Parser model observed as `unknown` in API responses.

This means the review package documents pipeline execution and OCR evidence, but **cannot yet propose confirmed employee identities or payroll amounts** for seeding. Human approval of any seed must wait until parser output is usable or fields are manually transcribed from OCR evidence.


## Environment

- **command:** `py scripts/dev/extract_fixture_review.py`
- **api_base:** `http://127.0.0.1:8000`
- **generated_at:** `2026-07-13T14:40:12.555719+00:00`
- **git_commit:** `ba478e4`
- **language_requested:** `he`
- **execution_mode:** `http_ocr_extract_then_parser_payslip`
- **db_writes:** `False`
- **ocr_engine_observed:** `tesseract`
- **ocr_language_effective_sample:** `heb+eng`
- **parser_model_observed:** `unknown`

## Source Files

- `valid/payslips_valid_2026_06_multi.pdf` — 266275 bytes — pages=7 — status=completed
- `invalid/payslips_invalid_2026_07_multi.pdf` — 282861 bytes — pages=7 — status=completed
- `valid/payslip_valid_2026_06_employee_001.png` — 91897 bytes — pages=1 — status=completed

## Payslip-by-Payslip Results

### valid_payslips_valid_2026_06_multi_p01

- **Source:** `valid/payslips_valid_2026_06_multi.pdf` page 1
- **Fixture intent:** valid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8689655172413793
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7736 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### valid_payslips_valid_2026_06_multi_p02

- **Source:** `valid/payslips_valid_2026_06_multi.pdf` page 2
- **Fixture intent:** valid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8700701754385964
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7725 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### valid_payslips_valid_2026_06_multi_p03

- **Source:** `valid/payslips_valid_2026_06_multi.pdf` page 3
- **Fixture intent:** valid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8707380073800738
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7754 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### valid_payslips_valid_2026_06_multi_p04

- **Source:** `valid/payslips_valid_2026_06_multi.pdf` page 4
- **Fixture intent:** valid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8703460207612457
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7746 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### valid_payslips_valid_2026_06_multi_p05

- **Source:** `valid/payslips_valid_2026_06_multi.pdf` page 5
- **Fixture intent:** valid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8650310559006211
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7638 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### valid_payslips_valid_2026_06_multi_p06

- **Source:** `valid/payslips_valid_2026_06_multi.pdf` page 6
- **Fixture intent:** valid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8674729241877256
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7751 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### valid_payslips_valid_2026_06_multi_p07

- **Source:** `valid/payslips_valid_2026_06_multi.pdf` page 7
- **Fixture intent:** valid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8662007168458782
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7701 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### invalid_payslips_invalid_2026_07_multi_p01

- **Source:** `invalid/payslips_invalid_2026_07_multi.pdf` page 1
- **Fixture intent:** invalid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8713058419243986
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7761 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### invalid_payslips_invalid_2026_07_multi_p02

- **Source:** `invalid/payslips_invalid_2026_07_multi.pdf` page 2
- **Fixture intent:** invalid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8692465753424657
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7761 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### invalid_payslips_invalid_2026_07_multi_p03

- **Source:** `invalid/payslips_invalid_2026_07_multi.pdf` page 3
- **Fixture intent:** invalid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8688686131386861
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7770 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### invalid_payslips_invalid_2026_07_multi_p04

- **Source:** `invalid/payslips_invalid_2026_07_multi.pdf` page 4
- **Fixture intent:** invalid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8725874125874126
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7778 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### invalid_payslips_invalid_2026_07_multi_p05

- **Source:** `invalid/payslips_invalid_2026_07_multi.pdf` page 5
- **Fixture intent:** invalid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8623582089552239
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7634 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### invalid_payslips_invalid_2026_07_multi_p06

- **Source:** `invalid/payslips_invalid_2026_07_multi.pdf` page 6
- **Fixture intent:** invalid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8776041666666666
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=3 selected_oem=3 quality_score=0.7807 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### invalid_payslips_invalid_2026_07_multi_p07

- **Source:** `invalid/payslips_invalid_2026_07_multi.pdf` page 7
- **Fixture intent:** invalid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.8665591397849463
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=11 selected_oem=3 quality_score=0.7745 candidates=4 processed_size=1654x2339
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

### valid_payslip_valid_2026_06_employee_001_p01

- **Source:** `valid/payslip_valid_2026_06_employee_001.png` page 1
- **Fixture intent:** valid
- **Masked national ID:** —
- **Employee name (raw):** —
- **Pay period (raw):** —
- **Extraction status:** ok
- **OCR engine / conf:** tesseract / 0.6542592592592592
- **Parser model / retry:** unknown / True

| Field | Review | Parser | Confidence | Raw | Source text |
|---|---|---|---|---|---|
| `employee_name` | MISSING | MISSING | None | — | — |
| `employee_id` | MISSING | MISSING | None | — | — |
| `employee_number` | MISSING | MISSING | None | — | — |
| `pay_period` | MISSING | MISSING | None | — | — |
| `employment_type` | MISSING | MISSING | None | — | — |
| `department` | MISSING | MISSING | None | — | — |
| `hourly_rate` | MISSING | MISSING | None | — | — |
| `base_salary` | MISSING | MISSING | None | — | — |
| `travel_expenses` | MISSING | MISSING | None | — | — |
| `regular_hours` | MISSING | MISSING | None | — | — |
| `overtime_hours` | MISSING | MISSING | None | — | — |
| `gross_salary` | MISSING | MISSING | None | — | — |
| `income_tax` | MISSING | MISSING | None | — | — |
| `national_insurance` | MISSING | MISSING | None | — | — |
| `health_tax` | MISSING | MISSING | None | — | — |
| `pension_employee` | MISSING | MISSING | None | — | — |
| `pension_employer` | MISSING | MISSING | None | — | — |
| `net_salary` | MISSING | MISSING | None | — | — |
| `vacation_balance` | MISSING | MISSING | None | — | — |
| `sick_leave_balance` | MISSING | MISSING | None | — | — |

**Warnings:**
- tesseract_strategy selected_psm=3 selected_oem=3 quality_score=0.6673 candidates=4 processed_size=1397x2000
- parser_semantic_invalid
- parser_semantic_retry_used
- parser_semantic_retry_failed
- Parser retried once after invalid JSON/schema response.

## Employee Grouping Proposal

### ungrouped_001

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_002

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_003

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_004

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_005

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_006

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_007

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_008

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_009

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_010

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_011

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_012

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_013

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_014

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

### ungrouped_015

- **Masked ID:** —
- **Names:** —
- **Employee numbers:** —
- **Grouping confidence:** none
- **Basis:** manual_review_required
- **Conflict:** {'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}

## PNG vs PDF Comparison

- **Best matching PDF page:** 1
- **OCR text Jaccard similarity:** 0.1463
- **Matching fields:** —
- **Differing fields:** —
- **Recommended review source (not approved):** pdf_page

Comparison only — do not auto-approve either source. PNG is documented as a screenshot of one valid multi-PDF payslip.

## Proposed Seed Structure

See `proposed_seed_schema.json` for the extensible preview. Not approved.

## Blocking Review Questions

- Grouping ungrouped_001: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_002: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_003: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_004: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_005: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_006: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_007: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_008: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_009: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_010: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_011: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_012: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_013: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_014: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- Grouping ungrouped_015: confidence=none conflicts=[{'type': 'not_auto_grouped', 'note': 'National ID missing/low-confidence/not CONFIRMED — manual review.'}]
- No employee master records should be created until national IDs and names are explicitly approved.
- Valid/invalid directory names are fixture intent only — do not treat extraction success as legal correctness.

