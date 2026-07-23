"""API route aggregation."""

from fastapi import APIRouter

from payroll_copilot.presentation.api.routes import (
    ai_monitoring,
    analytics,
    assistant,
    audit,
    auth,
    batch,
    catalog,
    compliance,
    document_lab,
    documents,
    employees,
    extraction,
    health,
    integrations,
    manual_review,
    ocr,
    parser,
    validation,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(employees.router, prefix="/employees", tags=["Employees"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["Catalog"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["Audit Logs"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(ocr.router, prefix="/ocr", tags=["OCR"])
api_router.include_router(parser.router, prefix="/parser", tags=["AI Parser"])
api_router.include_router(extraction.router, prefix="/extraction", tags=["Extraction"])
api_router.include_router(validation.router, prefix="/validation", tags=["Validation"])
api_router.include_router(document_lab.router, prefix="/dev/document-lab", tags=["Developer Document Lab"])
api_router.include_router(batch.router, prefix="/batch", tags=["Batch Processing"])
api_router.include_router(manual_review.router, prefix="/manual-review", tags=["Manual Review"])
api_router.include_router(compliance.router, prefix="/compliance", tags=["Compliance"])
api_router.include_router(assistant.router, prefix="/assistant", tags=["Assistant"])
api_router.include_router(ai_monitoring.router, prefix="/admin/ai", tags=["AI Monitoring"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["Integrations"])
