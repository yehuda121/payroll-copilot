"""Deferred complex Israeli payroll-law catalog (MVP Phase 1 out of scope).

These are intentionally NOT implemented as approximations.
"""

DEFERRED_COMPLEX_LAW: dict[str, str] = {
    "income_tax_engine": "Requires brackets, credits, cumulative YTD — Form 101 questionnaire.",
    "tax_credit_points": "Requires Form 101 / employee questionnaire answers.",
    "national_insurance": "Requires insured-wage reconstruction and contribution tables.",
    "taxable_salary_reconstruction": "Requires component classification beyond extracted gross.",
    "overtime_attendance_engine": "Requires attendance day reconstruction; payslip overtime_hours alone is insufficient for true daily OT.",
    "vacation_accrual": "Requires tenure, prior balances, and accrual conventions.",
    "sick_leave_payment": "Requires medical documentation and payment schedule rules.",
    "convalescence": "Requires seniority tiers and collective agreement variants.",
    "reserve_duty": "Requires reserve-duty documentation and payment formulas.",
    "travel_reimbursement": "Requires residence/route distance inputs.",
    "vehicle_benefit": "Requires vehicle model/year lookup tables.",
    "pension_contribution_percent": "Insured wage / eligibility month ambiguous; deferred (rule registered but inactive).",
    "employer_pension_minimum": "YAML present; no safe evaluator without contribution base.",
    "severance_component": "YAML present; termination/severance context required.",
    "training_fund_tax": "Complex benefit taxation.",
    "retroactive_payroll": "Requires multi-period adjustment engine.",
    "monthly_minimum_wage": "Partial-month / salary-basis proration not safely defined.",
    "seniority_years_derivation": "No product convention for start+period→years.",
    "contract_monthly_salary_exact": "Partial month / absence adjustments required for safe equality.",
    "contract_employment_scope": "Payslip 0–1 vs 0–100 representation unresolved.",
    "employee_chat_payslip_upload": "Chat has no payslip upload path; reuse Guest pipeline later.",
    "guest_supporting_contract_validation": "Guest supporting docs not confirmed employment-terms SoT yet.",
}
