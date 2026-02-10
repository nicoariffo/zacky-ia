"""FastAPI application entry point."""

from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Zacky IA API",
    description="AI-powered support assistant for Zendesk",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BackfillRequest(BaseModel):
    """Request model for backfill endpoint."""

    start_date: str | None = None
    resume: bool = True
    limit: int | None = None  # Limit number of tickets (for testing)


class PipelineRequest(BaseModel):
    """Request model for pipeline endpoint."""

    limit: int | None = None
    reprocess: bool = False


class QAReportRequest(BaseModel):
    """Request model for QA report endpoint."""

    sample_size: int = 100


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "message": "Zacky IA API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/zendesk/test")
async def test_zendesk_connection() -> dict[str, Any]:
    """Test connection to Zendesk API."""
    try:
        from src.ingestion.zendesk_client import ZendeskClient

        with ZendeskClient() as client:
            # Fetch just 1 ticket to verify connection
            count = 0
            for ticket, _ in client.iter_tickets(start_time=None, cursor=None):
                count += 1
                if count >= 1:
                    break

            return {
                "status": "connected",
                "subdomain": settings.zendesk_subdomain,
                "test_ticket_found": count > 0,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Zendesk connection failed: {e}")


@app.post("/ingestion/backfill")
async def run_backfill_endpoint(
    request: BackfillRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Trigger backfill job to ingest historical tickets from Zendesk."""
    from src.ingestion.backfill import run_backfill

    start_time = None
    if request.start_date:
        try:
            start_time = datetime.fromisoformat(request.start_date)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
            )

    # Run synchronously if limit is set (for testing), otherwise background
    if request.limit:
        try:
            result = run_backfill(start_time, request.resume, request.limit)
            return {
                "status": "completed",
                "message": f"Backfill completed: {result['total_processed']} tickets",
                "total_processed": result["total_processed"],
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Backfill failed: {e}")
    else:
        background_tasks.add_task(run_backfill, start_time, request.resume, None)
        return {
            "status": "started",
            "message": "Backfill job started in background",
            "start_date": request.start_date,
            "resume": str(request.resume),
        }


@app.post("/processing/pipeline")
async def run_pipeline_endpoint(
    request: PipelineRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Trigger processing pipeline to clean and redact PII from tickets."""
    from src.processing.pipeline import run_pipeline

    # Run synchronously if limit is set (for testing), otherwise background
    if request.limit:
        try:
            result = run_pipeline(request.limit, request.reprocess)
            return {
                "status": "completed",
                "message": f"Pipeline completed: {result['processed']} tickets",
                **result,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")
    else:
        background_tasks.add_task(run_pipeline, None, request.reprocess)
        return {
            "status": "started",
            "message": "Pipeline started in background",
            "reprocess": str(request.reprocess),
        }


@app.post("/processing/qa-report")
async def generate_qa_report_endpoint(request: QAReportRequest) -> dict[str, Any]:
    """Generate QA report on cleaning and PII redaction quality."""
    from src.processing.pipeline import generate_qa_report

    try:
        report = generate_qa_report(request.sample_size)
        return {
            "status": "success",
            "report": report,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QA report failed: {e}")
