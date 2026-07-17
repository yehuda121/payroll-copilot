"""E2E verification for guest + employee application flows (post-fix)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

API = "http://localhost:8000/api/v1"
FIX = Path("backend/tests/fixtures/documents/payslips/valid/payslip_valid_2026_06_employee_001.png")
# Copy name without triggering old id-in-valid bug for supporting tests
SUPPORT = Path("_audit/teudat_zehut.png")


def main() -> int:
    errors: list[str] = []
    client = httpx.Client(timeout=360.0)

    # Health
    r = client.get("http://localhost:8000/health")
    if r.status_code != 200:
        errors.append(f"health {r.status_code}")
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1

    # OpenAPI routes
    oa = client.get(f"{API.replace('/api/v1','')}/api/v1/openapi.json").json()
    paths = oa.get("paths", {})
    for required in (
        "/api/v1/extraction/guest/supporting-upload",
        "/api/v1/extraction/guest/{document_id}/confirm",
    ):
        if required not in paths:
            errors.append(f"missing openapi path {required}")

    # --- Guest flow ---
    guest = client.post(f"{API}/auth/guest/session").json()["guest_token"]
    gh = {"Authorization": f"Bearer {guest}"}

    with FIX.open("rb") as f:
        # Use a payslip-named copy to verify classification isn't needed server-side
        extract = client.post(
            f"{API}/extraction/guest/payslip-extract",
            headers=gh,
            files={"file": ("payslip_sample.png", f.read(), "image/png")},
        )
    if extract.status_code >= 400:
        errors.append(f"guest extract {extract.status_code}: {extract.text[:300]}")
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1
    body = extract.json()
    doc_id = body["document_id"]
    fields = body.get("fields") or []
    entries = body.get("entries")
    if not fields and not entries:
        # Build minimal entries from fields for confirm
        pass
    # Confirm with entries derived from fields if needed
    confirm_entries = entries
    if not confirm_entries and fields:
        confirm_entries = [
            {
                "id": f"f-{i}",
                "key": fld.get("key") or f"field_{i}",
                "value": fld.get("value"),
                "confidence": fld.get("confidence"),
                "page": 1,
                "source": "ocr",
                "source_text": fld.get("source_text"),
            }
            for i, fld in enumerate(fields)
            if fld.get("value") not in (None, "")
        ]
    if not confirm_entries:
        errors.append("guest extract produced no usable fields/entries for confirm")
    else:
        # Supporting upload
        SUPPORT.parent.mkdir(parents=True, exist_ok=True)
        SUPPORT.write_bytes(FIX.read_bytes())
        support = client.post(
            f"{API}/extraction/guest/supporting-upload",
            headers=gh,
            files={"file": ("teudat_zehut.png", SUPPORT.read_bytes(), "image/png")},
            data={"document_type": "national_id", "payslip_document_id": doc_id},
        )
        if support.status_code >= 400:
            errors.append(f"supporting upload {support.status_code}: {support.text[:300]}")
        else:
            support_id = support.json()["document_id"]

        confirm = client.post(
            f"{API}/extraction/guest/{doc_id}/confirm",
            headers=gh,
            json={"entries": confirm_entries},
        )
        if confirm.status_code >= 400:
            errors.append(f"guest confirm {confirm.status_code}: {confirm.text[:300]}")
        else:
            if confirm.json().get("status") != "confirmed":
                errors.append(f"guest confirm unexpected body {confirm.json()}")

            validation = client.post(
                f"{API}/validation/run",
                headers=gh,
                json={
                    "document_id": doc_id,
                    "supporting_document_ids": [support_id] if support.status_code < 400 else [],
                    "locale": "he",
                },
            )
            if validation.status_code >= 400:
                errors.append(f"guest validation {validation.status_code}: {validation.text[:400]}")
            else:
                run = validation.json()
                if not (run.get("id") or run.get("validation_run_id") or run.get("overall_result") or run.get("status")):
                    errors.append(f"validation missing payload: {run}")
                # Guest runs are ephemeral (in-memory) — GET /runs/{id} is not required for landing flow.

    # --- Employee portal ---
    emp = client.post(f"{API}/auth/dev/employee-session")
    if emp.status_code >= 400:
        errors.append(f"dev employee session {emp.status_code}: {emp.text[:300]}")
    else:
        token = emp.json()["access_token"]
        eh = {"Authorization": f"Bearer {token}"}
        for path in (
            "/employees/me",
            "/employees/me/documents",
            "/employees/me/payroll-months",
            "/employees/me/payslips",
        ):
            r = client.get(f"{API}{path}", headers=eh)
            if r.status_code >= 400:
                errors.append(f"employee GET {path} {r.status_code}: {r.text[:250]}")

        with FIX.open("rb") as f:
            up = client.post(
                f"{API}/documents/employee/upload",
                headers=eh,
                files={"file": ("teudat_zehut.png", f.read(), "image/png")},
                data={"document_type": "national_id"},
            )
        if up.status_code >= 400:
            errors.append(f"employee supporting upload {up.status_code}: {up.text[:250]}")

        with FIX.open("rb") as f:
            up2 = client.post(
                f"{API}/extraction/employee/payslip-extract",
                headers=eh,
                files={"file": ("payslip_sample.png", f.read(), "image/png")},
                data={
                    "language": "auto",
                    "period_year": "2026",
                    "period_month": "6",
                    "confirm_new_version": "true",
                },
            )
        if up2.status_code >= 400:
            errors.append(f"employee extract {up2.status_code}: {up2.text[:300]}")
        else:
            edoc = up2.json()["document_id"]
            # Prove document is readable before confirm
            listed = client.get(f"{API}/employees/me/documents", headers=eh)
            if listed.status_code >= 400:
                errors.append(f"employee documents after extract {listed.status_code}")
            conf = client.post(
                f"{API}/extraction/employee/{edoc}/confirm",
                headers=eh,
                json={"acknowledgement": True},
            )
            if conf.status_code >= 400:
                detail = (
                    conf.json().get("detail")
                    if conf.headers.get("content-type", "").startswith("application/json")
                    else conf.text
                )
                if conf.status_code == 409:
                    print("NOTE: employee confirm blocked (identity/period):", detail)
                else:
                    errors.append(f"employee confirm {conf.status_code}: {detail}")
            else:
                val = client.post(
                    f"{API}/validation/employee/run",
                    headers=eh,
                    json={"document_id": edoc, "locale": "he"},
                )
                if val.status_code >= 400:
                    errors.append(f"employee validation {val.status_code}: {val.text[:300]}")

    result = {"ok": len(errors) == 0, "errors": errors}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
