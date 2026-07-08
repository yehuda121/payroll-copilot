"""API route aggregation."""

from fastapi import APIRouter

from payroll_copilot.presentation.api.routes import (
    assistant,
    auth,
    batch,
    compliance,
    documents,
    extraction,
    health,
    integrations,
    ocr,
    parser,
    validation,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(ocr.router, prefix="/ocr", tags=["OCR"])
api_router.include_router(parser.router, prefix="/parser", tags=["AI Parser"])
api_router.include_router(extraction.router, prefix="/extraction", tags=["Extraction"])
api_router.include_router(validation.router, prefix="/validation", tags=["Validation"])
api_router.include_router(batch.router, prefix="/batch", tags=["Batch Processing"])
api_router.include_router(compliance.router, prefix="/compliance", tags=["Compliance"])
api_router.include_router(assistant.router, prefix="/assistant", tags=["Assistant"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["Integrations"])
