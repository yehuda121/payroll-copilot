"""Thin wrapper for local/Docker invocation outside the package import path."""

from payroll_copilot.scripts.seed_accountant_portal import main

if __name__ == "__main__":
    raise SystemExit(main())
