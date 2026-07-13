"""Manual review queue API for low-confidence employee matching."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from payroll_copilot.application.services.manual_review_queue import get_manual_review_queue

router = APIRouter()


class ResolveReviewRequest(BaseModel):
    status: str = Field(
        description="resolved_create | resolved_attach | dismissed",
        pattern="^(resolved_create|resolved_attach|dismissed)$",
    )
    notes: str | None = Field(default=None, max_length=1000)


@router.get("")
async def list_manual_review(pending_only: bool = True) -> list[dict]:
    queue = get_manual_review_queue()
    items = queue.list_pending() if pending_only else queue.list_all()
    return [item.to_dict() for item in items]


@router.post("/{item_id}/resolve")
async def resolve_manual_review(item_id: str, body: ResolveReviewRequest) -> dict:
    queue = get_manual_review_queue()
    item = queue.resolve(item_id, status=body.status, notes=body.notes)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found")
    return item.to_dict()
