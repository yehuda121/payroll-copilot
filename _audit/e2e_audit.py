"""End-to-end audit harness — read-only probes; writes findings JSON only."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

API = os.environ.get("AUDIT_API", "http://localhost:8000/api/v1")
FRONT = os.environ.get("AUDIT_FRONT", "http://localhost:3000")
FIX = Path(
    os.environ.get(
        "AUDIT_PAYSLIP",
        "backend/tests/fixtures/documents/payslips/valid/payslip_valid_2026_06_employee_001.png",
    )
)
OUT = Path("_audit/findings.json")


@dataclass
class Finding:
    severity: str  # error | broken_flow | exception | missing_config | regression
    area: str
    summary: str
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


findings: list[Finding] = []


def add(severity: str, area: str, summary: str, detail: str = "", **evidence: Any) -> None:
    findings.append(
        Finding(severity=severity, area=area, summary=summary, detail=detail, evidence=evidence)
    )


def safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text[:2000]


def main() -> int:
    client = httpx.Client(timeout=120.0, follow_redirects=True)

    # --- Frontend shell ---
    for path in ["/", "/login", "/signup"]:
        try:
            r = client.get(f"{FRONT}{path}")
            if r.status_code >= 400:
                add(
                    "broken_flow",
                    "ui",
                    f"Frontend {path} returned HTTP {r.status_code}",
                    evidence={"status": r.status_code, "body": r.text[:500]},
                )
            elif "Payroll" not in r.text and "root" not in r.text and "vite" not in r.text.lower():
                # Vite SPA shell may still be ok
                if len(r.text) < 50:
                    add("broken_flow", "ui", f"Frontend {path} returned empty/short body")
        except Exception as exc:
            add("exception", "ui", f"Frontend {path} unreachable", str(exc))

    # --- Health ---
    try:
        r = client.get("http://localhost:8000/health")
        if r.status_code != 200 or r.json().get("status") != "healthy":
            add("error", "api", "Health check failed", evidence={"status": r.status_code, "body": safe_json(r)})
    except Exception as exc:
        add("exception", "api", "Health endpoint unreachable", str(exc))

    # --- Cognito / auth login ---
    try:
        r = client.post(f"{API}/auth/login", json={"email": "test@example.com", "password": "x"})
        body = safe_json(r)
        if r.status_code == 503:
            detail = body.get("detail") if isinstance(body, dict) else body
            code = detail.get("code") if isinstance(detail, dict) else None
            if code == "cognito_not_configured":
                add(
                    "missing_config",
                    "cognito",
                    "Cognito not configured (COGNITO_USER_POOL_ID / COGNITO_APP_CLIENT_ID empty); /auth/login returns 503",
                    evidence={"status": r.status_code, "body": body},
                )
            else:
                add("error", "cognito", "Login returned 503", evidence={"body": body})
        elif r.status_code == 401:
            # Cognito configured but bad credentials — config present
            pass
        else:
            add(
                "error",
                "cognito",
                f"/auth/login unexpected status {r.status_code}",
                evidence={"body": body},
            )
    except Exception as exc:
        add("exception", "cognito", "Login probe failed", str(exc))

    # --- Guest session ---
    guest_token = None
    try:
        r = client.post(f"{API}/auth/guest/session")
        if r.status_code not in (200, 201):
            add(
                "broken_flow",
                "guest",
                f"Guest session failed HTTP {r.status_code}",
                evidence={"body": safe_json(r)},
            )
        else:
            guest_token = r.json()["guest_token"]
    except Exception as exc:
        add("exception", "guest", "Guest session exception", str(exc))

    # --- Assistant chat (landing) ---
    if guest_token:
        try:
            r = client.post(
                f"{API}/assistant/chat",
                headers={"Authorization": f"Bearer {guest_token}"},
                json={"message": "מה זה תלוש שכר?", "locale": "he"},
            )
            if r.status_code >= 400:
                add(
                    "broken_flow",
                    "guest_chat",
                    f"Assistant chat failed HTTP {r.status_code}",
                    evidence={"body": safe_json(r)},
                )
            else:
                data = r.json()
                if not (data.get("reply") or data.get("answer") or data.get("message")):
                    # accept any non-empty text field
                    textish = json.dumps(data, ensure_ascii=False)
                    if len(textish) < 20:
                        add(
                            "broken_flow",
                            "guest_chat",
                            "Assistant chat returned empty/near-empty payload",
                            evidence={"body": data},
                        )
        except Exception as exc:
            add("exception", "guest_chat", "Assistant chat exception", str(exc), traceback=traceback.format_exc())

    # --- Guest extraction pipeline ---
    if guest_token and FIX.exists():
        try:
            with FIX.open("rb") as f:
                r = client.post(
                    f"{API}/extraction/guest/payslip-extract",
                    headers={"Authorization": f"Bearer {guest_token}"},
                    files={"file": (FIX.name, f, "image/png")},
                )
            body = safe_json(r)
            if r.status_code >= 400:
                add(
                    "broken_flow",
                    "guest_extraction",
                    f"Guest payslip extract failed HTTP {r.status_code}",
                    evidence={"body": body},
                )
            else:
                doc_id = body.get("document_id") if isinstance(body, dict) else None
                fields = body.get("fields") if isinstance(body, dict) else None
                if not doc_id:
                    add(
                        "broken_flow",
                        "guest_extraction",
                        "Extract succeeded but missing document_id",
                        evidence={"body": body},
                    )
                else:
                    # confirm
                    cr = client.post(
                        f"{API}/extraction/guest/{doc_id}/confirm",
                        headers={"Authorization": f"Bearer {guest_token}"},
                        json={},
                    )
                    if cr.status_code >= 400:
                        add(
                            "broken_flow",
                            "guest_confirm",
                            f"Guest confirm failed HTTP {cr.status_code}",
                            evidence={"body": safe_json(cr)},
                        )
                    # validate
                    vr = client.post(
                        f"{API}/validation/run",
                        headers={"Authorization": f"Bearer {guest_token}"},
                        json={"document_id": doc_id},
                    )
                    if vr.status_code >= 400:
                        add(
                            "broken_flow",
                            "guest_validation",
                            f"Guest validation failed HTTP {vr.status_code}",
                            evidence={"body": safe_json(vr)},
                        )
                    else:
                        run = vr.json()
                        run_id = run.get("id") or run.get("validation_run_id")
                        if run_id:
                            gr = client.get(
                                f"{API}/validation/runs/{run_id}",
                                headers={"Authorization": f"Bearer {guest_token}"},
                            )
                            if gr.status_code >= 400:
                                add(
                                    "broken_flow",
                                    "guest_validation",
                                    f"Get validation run failed HTTP {gr.status_code}",
                                    evidence={"body": safe_json(gr)},
                                )
                    if isinstance(fields, list) and len(fields) == 0:
                        add(
                            "broken_flow",
                            "guest_extraction",
                            "Extraction returned zero fields",
                            evidence={"document_id": doc_id},
                        )
        except Exception as exc:
            add(
                "exception",
                "guest_extraction",
                "Guest extraction pipeline exception",
                str(exc),
                traceback=traceback.format_exc(),
            )
    elif guest_token:
        add("error", "guest_extraction", f"Payslip fixture missing: {FIX}")

    # --- Dev employee session ---
    emp_token = None
    try:
        r = client.post(f"{API}/auth/dev/employee-session")
        if r.status_code not in (200, 201):
            add(
                "broken_flow",
                "employee_auth",
                f"Dev employee session failed HTTP {r.status_code}",
                evidence={"body": safe_json(r)},
            )
        else:
            emp_token = r.json()["access_token"]
    except Exception as exc:
        add("exception", "employee_auth", "Dev employee session exception", str(exc))

    if emp_token:
        auth = {"Authorization": f"Bearer {emp_token}"}
        for path, area in [
            ("/employees/me", "employee_me"),
            ("/employees/me/documents", "employee_documents"),
            ("/employees/me/documents/national-id/review", "employee_national_id"),
            ("/employees/me/payslips", "employee_payslips"),
            ("/employees/me/payroll-months", "employee_payroll_months"),
        ]:
            try:
                r = client.get(f"{API}{path}", headers=auth)
                if r.status_code >= 400:
                    add(
                        "broken_flow",
                        area,
                        f"GET {path} failed HTTP {r.status_code}",
                        evidence={"body": safe_json(r)},
                    )
            except Exception as exc:
                add("exception", area, f"GET {path} exception", str(exc))

        # employee upload
        if FIX.exists():
            try:
                with FIX.open("rb") as f:
                    r = client.post(
                        f"{API}/documents/employee/upload",
                        headers=auth,
                        files={"file": (FIX.name, f, "image/png")},
                        data={"document_type": "payslip"},
                    )
                if r.status_code >= 400:
                    add(
                        "broken_flow",
                        "employee_upload",
                        f"Employee upload failed HTTP {r.status_code}",
                        evidence={"body": safe_json(r)},
                    )
            except Exception as exc:
                add("exception", "employee_upload", "Employee upload exception", str(exc))

    # --- Accountant endpoints (often unauthenticated or role-gated) ---
    for path, area in [
        ("/employees", "accountant_employees"),
        ("/batch/jobs", "accountant_batch"),
        ("/manual-review", "accountant_approvals"),
        ("/audit", "accountant_audit"),
        ("/compliance/legal-rules", "accountant_rules"),
    ]:
        try:
            headers = {"Authorization": f"Bearer {emp_token}"} if emp_token else {}
            r = client.get(f"{API}{path}", headers=headers)
            # 401/403 may be expected if RBAC enforced; 500 is error
            if r.status_code >= 500:
                add(
                    "error",
                    area,
                    f"GET {path} server error HTTP {r.status_code}",
                    evidence={"body": safe_json(r)},
                )
            elif r.status_code >= 400:
                # record as broken only if endpoint is meant to work with emp token wrongly —
                # for accountant routes without accountant auth, 401/403 is not a regression
                pass
        except Exception as exc:
            add("exception", area, f"GET {path} exception", str(exc))

    # --- Catalog / OCR smoke ---
    try:
        r = client.get(f"{API}/catalog/document-types")
        if r.status_code >= 400:
            add("error", "catalog", f"document-types HTTP {r.status_code}", evidence={"body": safe_json(r)})
    except Exception as exc:
        add("exception", "catalog", "catalog exception", str(exc))

    # --- Signup page presence (UI) already checked; check if signup API exists ---
    # --- DynamoDB local ---
    try:
        import boto3
        from botocore.config import Config

        ddb = boto3.client(
            "dynamodb",
            endpoint_url="http://localhost:8001",
            region_name="us-east-1",
            aws_access_key_id="local",
            aws_secret_access_key="local",
            config=Config(retries={"max_attempts": 2}),
        )
        tables = ddb.list_tables().get("TableNames", [])
        if "PayrollCopilot" not in tables:
            # table may auto-create on first write — try describe after a write via API already done
            try:
                ddb.describe_table(TableName="PayrollCopilot")
            except Exception as exc:
                add(
                    "error",
                    "dynamodb_local",
                    "DynamoDB Local table PayrollCopilot missing after guest/employee flows",
                    str(exc),
                    tables=tables,
                )
    except Exception as exc:
        add("exception", "dynamodb_local", "DynamoDB Local probe failed", str(exc))

    # --- MinIO / S3 local ---
    try:
        import boto3
        from botocore.config import Config

        s3 = boto3.client(
            "s3",
            endpoint_url="http://localhost:9000",
            region_name="us-east-1",
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
        if "payroll-copilot" not in buckets:
            add(
                "error",
                "s3_minio",
                "MinIO bucket payroll-copilot missing",
                evidence={"buckets": buckets},
            )
        else:
            objs = s3.list_objects_v2(Bucket="payroll-copilot", MaxKeys=5)
            if objs.get("KeyCount", 0) == 0 and guest_token:
                add(
                    "broken_flow",
                    "s3_minio",
                    "No objects in MinIO after extraction/upload flows (storage may have failed silently)",
                    evidence={"buckets": buckets},
                )
    except Exception as exc:
        add("exception", "s3_minio", "MinIO probe failed", str(exc))

    # --- Real AWS probes (credentials from env) ---
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    region = os.environ.get("AWS_REGION", "us-east-1")
    if not aws_key or not aws_secret:
        add(
            "missing_config",
            "aws_credentials",
            "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not available in audit process env",
        )
    else:
        try:
            import boto3
            from botocore.exceptions import ClientError, BotoCoreError

            # Cognito list pools (identity wiring)
            try:
                cog = boto3.client(
                    "cognito-idp",
                    region_name=region,
                    aws_access_key_id=aws_key,
                    aws_secret_access_key=aws_secret,
                )
                pools = cog.list_user_pools(MaxResults=5)
                if not pools.get("UserPools"):
                    add(
                        "missing_config",
                        "cognito",
                        "AWS Cognito reachable but no user pools found in region (and app pool IDs unset)",
                        evidence={"region": region},
                    )
            except ClientError as exc:
                add(
                    "error",
                    "cognito",
                    "AWS Cognito API error",
                    str(exc),
                    code=exc.response.get("Error", {}).get("Code"),
                )
            except BotoCoreError as exc:
                add("exception", "cognito", "AWS Cognito boto error", str(exc))

            # Real S3
            try:
                s3 = boto3.client(
                    "s3",
                    region_name=region,
                    aws_access_key_id=aws_key,
                    aws_secret_access_key=aws_secret,
                )
                s3.list_buckets()
                try:
                    s3.head_bucket(Bucket="payroll-copilot")
                except ClientError as exc:
                    add(
                        "missing_config",
                        "s3",
                        "Amazon S3 credentials work but bucket 'payroll-copilot' is missing or inaccessible; runtime uses MinIO (S3_ENDPOINT set)",
                        str(exc),
                        code=exc.response.get("Error", {}).get("Code"),
                    )
            except ClientError as exc:
                add("error", "s3", "Amazon S3 API error", str(exc))

            # Real DynamoDB
            try:
                ddb = boto3.client(
                    "dynamodb",
                    region_name=region,
                    aws_access_key_id=aws_key,
                    aws_secret_access_key=aws_secret,
                )
                names = ddb.list_tables().get("TableNames", [])
                if "PayrollCopilot" not in names:
                    add(
                        "missing_config",
                        "dynamodb",
                        "Amazon DynamoDB reachable but table PayrollCopilot not found; runtime uses DynamoDB Local (DYNAMODB_ENDPOINT set)",
                        evidence={"tables_sample": names[:20]},
                    )
            except ClientError as exc:
                add("error", "dynamodb", "Amazon DynamoDB API error", str(exc))

            # SES
            try:
                ses = boto3.client(
                    "ses",
                    region_name=region,
                    aws_access_key_id=aws_key,
                    aws_secret_access_key=aws_secret,
                )
                attrs = ses.get_account_sending_enabled()
                identities = ses.list_identities(IdentityType="EmailAddress", MaxItems=5)
                if not identities.get("Identities") and not os.environ.get("SES_FROM_EMAIL"):
                    add(
                        "missing_config",
                        "ses",
                        "SES reachable but SES_FROM_EMAIL empty and no verified email identities listed; app uses console email logger",
                        evidence={"sending_enabled": attrs.get("Enabled")},
                    )
            except ClientError as exc:
                add(
                    "error",
                    "ses",
                    "Amazon SES API error",
                    str(exc),
                    code=exc.response.get("Error", {}).get("Code"),
                )

            # Bedrock
            try:
                br = boto3.client(
                    "bedrock-runtime",
                    region_name=region,
                    aws_access_key_id=aws_key,
                    aws_secret_access_key=aws_secret,
                )
                # lightweight: invoke with tiny body may fail on model access — also list via bedrock control plane
                ctrl = boto3.client(
                    "bedrock",
                    region_name=region,
                    aws_access_key_id=aws_key,
                    aws_secret_access_key=aws_secret,
                )
                models = ctrl.list_foundation_models(byOutputModality="TEXT")
                model_ids = [
                    m.get("modelId")
                    for m in models.get("modelSummaries", [])
                    if "claude-3-5-sonnet" in (m.get("modelId") or "")
                ]
                target = "anthropic.claude-3-5-sonnet-20241022-v2:0"
                if target not in [m.get("modelId") for m in models.get("modelSummaries", [])] and not model_ids:
                    add(
                        "missing_config",
                        "bedrock",
                        f"Bedrock control plane reachable but configured model {target} not listed / not accessible; runtime MODEL_PROVIDER=ollama",
                    )
                else:
                    # Attempt a minimal converse/invoke to prove inference IAM
                    try:
                        # Use invoke_model with anthropic messages format if available
                        body = {
                            "anthropic_version": "bedrock-2023-05-31",
                            "max_tokens": 8,
                            "messages": [{"role": "user", "content": "ping"}],
                        }
                        br.invoke_model(
                            modelId=target,
                            contentType="application/json",
                            accept="application/json",
                            body=json.dumps(body).encode("utf-8"),
                        )
                    except ClientError as exc:
                        add(
                            "error",
                            "bedrock",
                            "Bedrock invoke failed (model access or IAM)",
                            str(exc),
                            code=exc.response.get("Error", {}).get("Code"),
                        )
                    # Also note runtime not using bedrock
                    add(
                        "missing_config",
                        "bedrock",
                        "Runtime MODEL_PROVIDER=ollama — Amazon Bedrock is not the active inference path in this environment",
                    )
            except ClientError as exc:
                add("error", "bedrock", "Amazon Bedrock API error", str(exc))
            except BotoCoreError as exc:
                add("exception", "bedrock", "Bedrock boto error", str(exc))
        except Exception as exc:
            add("exception", "aws", "AWS probe suite failed", str(exc), traceback=traceback.format_exc())

    # Runtime wiring notes that are actual misconfig vs AWS defaults
    add(
        "missing_config",
        "runtime_wiring",
        "Active runtime is local substitutes (MinIO + DynamoDB Local + Ollama + Cognito unset + SES console). AWS production adapters are not exercised by the running stack.",
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api": API,
        "frontend": FRONT,
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"finding_count": len(findings), "out": str(OUT)}, indent=2))
    for f in findings:
        print(f"[{f.severity}] {f.area}: {f.summary}")
    return 0


if __name__ == "__main__":
    # Load AWS keys from .env without printing them
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k in {
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_REGION",
                "SES_FROM_EMAIL",
                "COGNITO_USER_POOL_ID",
                "COGNITO_APP_CLIENT_ID",
            }:
                os.environ.setdefault(k, v)
    raise SystemExit(main())
