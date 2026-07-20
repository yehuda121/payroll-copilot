"""Application-layer validation orchestration and context builders.

Domain rules live under ``domain.rules``. Persistence of validation runs/findings
is infrastructure. Import concrete modules directly (e.g.
``application.validation.orchestrator``) to avoid circular imports with use cases.
"""
