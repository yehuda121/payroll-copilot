# Accountant Portal development seed

Version-controlled dataset: `accountant_portal_seed.json`

- `dataset_id`: `accountant_portal_seed_v1`
- `dataset_version`: `1.0`
- Source of truth: verified PDF values (no OCR/parser output)

## Docker commands

Seed (idempotent):

```bash
docker compose exec api python -m payroll_copilot.scripts.seed_accountant_portal
```

Cleanup (only this dataset):

```bash
docker compose exec api python -m payroll_copilot.scripts.seed_accountant_portal --cleanup
```

Blocked when `APP_ENV` is `production` or `prod`.

---

# Demo company seed (Digital Payslips + validation)

See also [`docs/demo-company-seed.md`](../../../docs/demo-company-seed.md).

```bash
docker compose exec api python -m payroll_copilot.scripts.seed_demo_company
```

Tops the demo org to ~10 employees, fills Jan→current-month Digital Payslips, creates digital ID/appendix/contract extractions (no files), and runs the real validation pipeline. Additive only.
