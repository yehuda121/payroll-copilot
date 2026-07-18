"""Port for object storage uploads."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStoragePort(Protocol):
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        ...

    async def delete(self, key: str) -> None:
        ...
