"""Port for object storage uploads."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStoragePort(Protocol):
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        ...

    async def download(self, key: str) -> bytes:
        ...

    async def delete(self, key: str) -> None:
        ...

    async def list_keys(self, prefix: str) -> list[str]:
        """List object keys under a prefix (empty list when unsupported/empty)."""
        ...

    async def delete_prefix(self, prefix: str) -> int:
        """Delete all objects under prefix; return deleted count."""
        ...
