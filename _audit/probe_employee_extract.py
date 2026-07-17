import json
from pathlib import Path

import httpx

API = "http://localhost:8000/api/v1"
FIX = Path("backend/tests/fixtures/documents/payslips/valid/payslip_valid_2026_06_employee_001.png")

c = httpx.Client(timeout=180)
emp = c.post(f"{API}/auth/dev/employee-session").json()
h = {"Authorization": f"Bearer {emp['access_token']}"}
with FIX.open("rb") as f:
    r = c.post(
        f"{API}/extraction/employee/payslip-extract",
        headers=h,
        files={"file": ("payslip.png", f.read(), "image/png")},
        data={
            "language": "auto",
            "period_year": "2026",
            "period_month": "6",
            "confirm_new_version": "true",
        },
    )
print("status", r.status_code)
body = r.json()
print(
    json.dumps(
        {
            k: body.get(k)
            for k in [
                "document_id",
                "extraction_id",
                "ocr_status",
                "parser_status",
                "error_message",
                "warnings",
                "blocks_confirmation",
            ]
        },
        indent=2,
    )
)
fields = body.get("fields") or []
print("fields", len(fields))
print("sample keys", [f.get("key") for f in fields[:12]])
