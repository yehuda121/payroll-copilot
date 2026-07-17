"""Object storage adapters (Amazon S3)."""

from payroll_copilot.infrastructure.storage.factory import create_object_storage
from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage

__all__ = ["S3ObjectStorage", "create_object_storage"]
