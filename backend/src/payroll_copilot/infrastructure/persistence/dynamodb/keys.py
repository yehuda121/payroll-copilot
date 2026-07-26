"""DynamoDB single-table key helpers (PayrollCopilot)."""

from __future__ import annotations

import hashlib
from uuid import UUID


def org_pk(organization_id: UUID | str) -> str:
    return f"ORG#{organization_id}"


def emp_sk(employee_id: UUID | str) -> str:
    return f"EMP#{employee_id}"


def emp_pk(organization_id: UUID | str, employee_id: UUID | str) -> str:
    return f"ORG#{organization_id}#EMP#{employee_id}"


def user_sk(user_id: UUID | str) -> str:
    return f"USER#{user_id}"


def dept_sk(department_id: UUID | str) -> str:
    return f"DEPT#{department_id}"


def doc_sk(
    *,
    document_type: str,
    period_year: int | None,
    period_month: int | None,
    document_id: UUID | str,
) -> str:
    if period_year is not None and period_month is not None:
        period = f"{period_year:04d}-{period_month:02d}"
    else:
        period = "none"
    return f"DOC#{document_type}#{period}#{document_id}"


def guest_doc_sk(document_id: UUID | str) -> str:
    return f"DOC#GUEST#{document_id}"


def ext_sk(*, version: int, extraction_id: UUID | str) -> str:
    return f"EXT#{version:08d}#{extraction_id}"


def valrun_sk(*, sort_key: str, run_id: UUID | str) -> str:
    return f"VALRUN#{sort_key}#{run_id}"


def valfind_sk(finding_id: UUID | str) -> str:
    return f"VALFIND#{finding_id}"


def audit_sk(*, sort_key: str, audit_id: str) -> str:
    return f"AUDIT#{sort_key}#{audit_id}"


def gsi1_doc(document_id: UUID | str) -> str:
    return f"DOC#{document_id}"


def gsi1_emp(employee_id: UUID | str) -> str:
    return f"EMP#{employee_id}"


def gsi1_user(user_id: UUID | str) -> str:
    return f"USER#{user_id}"


def gsi1_ext(extraction_id: UUID | str) -> str:
    return f"EXT#{extraction_id}"


def gsi1_valrun(run_id: UUID | str) -> str:
    return f"VALRUN#{run_id}"


def gsi1_dept(department_id: UUID | str) -> str:
    return f"DEPT#{department_id}"


def gsi2_national_id(organization_id: UUID | str, national_id_hash: str) -> str:
    return f"ORG#{organization_id}#NID#{national_id_hash}"


def gsi2_emp_number(organization_id: UUID | str, employee_number: str) -> str:
    return f"ORG#{organization_id}#EMPNO#{employee_number}"


def gsi3_dataset(dataset_id: str) -> str:
    return f"DATASET#{dataset_id}"


def vac_sk(vacation_id: UUID | str) -> str:
    return f"VAC#{vacation_id}"


def gsi1_vac(vacation_id: UUID | str) -> str:
    return f"VAC#{vacation_id}"


def gsi2_vac_message(
    organization_id: UUID | str,
    provider: str,
    provider_message_id: str,
) -> str:
    return f"ORG#{organization_id}#VMSG#{provider}#{provider_message_id}"


def gsi3_vac_employee(organization_id: UUID | str, employee_id: UUID | str | None) -> str:
    emp = "NONE" if employee_id is None else str(employee_id)
    return f"ORG#{organization_id}#VEMP#{emp}"


def vac_settings_sk() -> str:
    return "VAC_SETTINGS"


def vac_otp_sk(*, purpose: str, email: str) -> str:
    return f"EMAIL_OTP#{purpose}#{email.strip().lower()}"


def vac_pipe_sk(day: str) -> str:
    """day = YYYY-MM-DD UTC."""
    return f"VAC_PIPE#{day}"


def vac_event_dedup_sk(event_id: str) -> str:
    return f"VAC_EVTDEDUP#{event_id}"


def integration_cred_sk(credential_id: UUID | str) -> str:
    return f"INTEGRATION#{credential_id}"


def gsi2_integration_key_hash(key_hash: str) -> str:
    return f"INTKEY#{key_hash}"


def sick_sk(sick_leave_id: UUID | str) -> str:
    return f"SICK#{sick_leave_id}"


def gsi1_sick(sick_leave_id: UUID | str) -> str:
    return f"SICK#{sick_leave_id}"


def gsi2_sick_message(
    organization_id: UUID | str,
    provider: str,
    provider_message_id: str,
) -> str:
    return f"ORG#{organization_id}#SMSG#{provider}#{provider_message_id}"


def gsi3_sick_employee(organization_id: UUID | str, employee_id: UUID | str | None) -> str:
    emp = "NONE" if employee_id is None else str(employee_id)
    return f"ORG#{organization_id}#SEMP#{emp}"


def leave_idemp_sk(domain: str, provider: str, provider_message_id: str) -> str:
    """Org-scoped leave ingest idempotency sort key (hash avoids delimiter issues).

    domain is ``vacation`` or ``sick_leave``. PK remains ``ORG#{organization_id}``.
    """
    digest = hashlib.sha256(
        f"{provider.strip().lower()}\0{provider_message_id.strip()}".encode("utf-8")
    ).hexdigest()
    return f"LEAVE_IDEMP#{domain}#{digest}"
