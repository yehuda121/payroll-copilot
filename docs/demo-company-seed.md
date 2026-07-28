# Demo company development seed

Additive, development-only dataset for presentations.

## What it creates

- Tops the **demo organization** up to about **10 employees** (never deletes / overwrites).
- Assigns new employees to the local demo payroll accountant.
- For demo profiles: confirmed digital **National ID**, **ID Appendix** (children), and **Employment Contract** extractions (no PDF/OCR/S3 uploads).
- Digital Payslips for **January → current month** of the current year only.
- Runs the **production validation pipeline** after each new payslip.

## Command

```bash
docker compose exec api python -m payroll_copilot.scripts.seed_demo_company
```

Dry run:

```bash
docker compose exec api python -m payroll_copilot.scripts.seed_demo_company --dry-run
```

Blocked when `APP_ENV` is `production` or `prod`.
