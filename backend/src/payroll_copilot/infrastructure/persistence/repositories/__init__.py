"""Legacy SQLAlchemy repository adapters.

Runtime persistence is DynamoDB (``infrastructure.persistence.dynamodb``).
These adapters remain for optional Alembic / DATABASE_URL tooling only.
Do not wire new application paths to SQLAlchemy repositories.
"""
