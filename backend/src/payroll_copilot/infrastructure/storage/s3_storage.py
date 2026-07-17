"""Amazon S3 object storage adapter.

Supports:
- Amazon S3 (default): empty endpoint, IAM role / default credential chain
- S3-compatible local stores (e.g. MinIO): custom endpoint + static keys
"""

from __future__ import annotations

import io
import logging
from typing import Any

import boto3
from botocore.client import BaseClient, Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3ObjectStorage:
    """Object storage backed by Amazon S3 (or an S3-compatible endpoint)."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str = "us-east-1",
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        use_ssl: bool = True,
        auto_create_bucket: bool = False,
    ) -> None:
        if not bucket or not bucket.strip():
            raise ValueError("S3 bucket name is required.")

        self._bucket = bucket.strip()
        self._region = region
        self._endpoint = (endpoint or "").strip() or None
        self._client = self._build_client(
            region=region,
            endpoint=self._endpoint,
            access_key=(access_key or "").strip() or None,
            secret_key=(secret_key or "").strip() or None,
            use_ssl=use_ssl,
        )
        if auto_create_bucket:
            self._ensure_bucket()
        else:
            self._assert_bucket_exists()

    @staticmethod
    def _build_client(
        *,
        region: str,
        endpoint: str | None,
        access_key: str | None,
        secret_key: str | None,
        use_ssl: bool,
    ) -> BaseClient:
        # Custom endpoints (MinIO) typically need path-style addressing.
        # Amazon S3 prefers virtual-hosted–style.
        addressing = "path" if endpoint else "virtual"
        config = Config(
            signature_version="s3v4",
            s3={"addressing_style": addressing},
        )
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": region,
            "config": config,
        }
        if endpoint:
            kwargs["endpoint_url"] = endpoint
            kwargs["use_ssl"] = use_ssl
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        # When keys are omitted, boto3 uses the default credential chain
        # (env vars, shared config, IAM role, etc.).
        return boto3.client(**kwargs)

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            logger.info("Creating object storage bucket %s", self._bucket)
            params: dict[str, Any] = {"Bucket": self._bucket}
            # us-east-1 does not accept LocationConstraint.
            if self._region and self._region != "us-east-1":
                params["CreateBucketConfiguration"] = {"LocationConstraint": self._region}
            try:
                self._client.create_bucket(**params)
            except ClientError:
                # Race or already exists after head failure — re-check.
                self._client.head_bucket(Bucket=self._bucket)

    def _assert_bucket_exists(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            raise RuntimeError(
                f"S3 bucket '{self._bucket}' is not accessible. "
                "Create the bucket and grant the runtime role/user "
                "s3:ListBucket, s3:GetObject, s3:PutObject, s3:DeleteObject."
            ) from exc

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        extra_args = {"ContentType": content_type} if content_type else None
        self._client.upload_fileobj(
            io.BytesIO(data),
            self._bucket,
            key,
            ExtraArgs=extra_args,
        )
        return key

    async def download(self, key: str) -> bytes:
        buffer = io.BytesIO()
        self._client.download_fileobj(self._bucket, key, buffer)
        return buffer.getvalue()

    async def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    async def generate_presigned_url(self, key: str, expires_seconds: int = 300) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
