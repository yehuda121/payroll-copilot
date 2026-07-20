"""Bounded upload reads — reject oversize payloads before buffering the full file."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

_DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MiB


async def read_upload_with_size_limit(
    upload: UploadFile,
    max_size_bytes: int,
    *,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> bytes:
    """Read an upload in chunks and fail as soon as ``max_size_bytes`` is exceeded."""
    if max_size_bytes <= 0:
        raise ValueError("max_size_bytes must be positive")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": "file_too_large",
                    "message": f"File exceeds maximum size of {max_size_bytes // (1024 * 1024)}MB",
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)
