"""Factory for the document object-storage adapter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from payroll_copilot.infrastructure.config.service_resolver import get_resolved_s3_endpoint
from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage

if TYPE_CHECKING:
    from payroll_copilot.infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)


def create_object_storage(settings: Settings) -> S3ObjectStorage:
    """Build S3ObjectStorage from application settings.

    - Empty ``S3_ENDPOINT`` → Amazon S3 (regional AWS endpoint + default credentials).
    - Non-empty endpoint → S3-compatible store (e.g. MinIO), with optional local fallback.
    - Bucket auto-create applies only when using a custom endpoint (local/dev).
    """
    endpoint = get_resolved_s3_endpoint(settings)
    using_custom_endpoint = bool(endpoint)

    # Never auto-create buckets against Amazon S3 from the application runtime.
    if using_custom_endpoint:
        auto_create = bool(settings.s3_auto_create_bucket)
        use_ssl = bool(settings.s3_use_ssl)
    else:
        auto_create = False
        use_ssl = True

    logger.info(
        "Object storage: bucket=%s region=%s endpoint=%s auto_create_bucket=%s",
        settings.s3_bucket,
        settings.s3_region,
        endpoint or "aws",
        auto_create,
    )

    return S3ObjectStorage(
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        endpoint=endpoint or None,
        access_key=settings.s3_access_key or None,
        secret_key=settings.s3_secret_key or None,
        use_ssl=use_ssl,
        auto_create_bucket=auto_create,
        server_side_encryption=(
            getattr(settings, "s3_server_side_encryption", "") or ""
        ).strip()
        or None,
    )
