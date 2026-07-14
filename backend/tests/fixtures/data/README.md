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
