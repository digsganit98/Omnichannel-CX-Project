from fastapi import APIRouter

from services.analytics_service.consolidated_records import (
    load_consolidated_records,
    load_uploaded_records,
    summarize_consolidated_records,
)

router = APIRouter(prefix="/synthetic", tags=["synthetic"])


@router.get("/records")
def list_synthetic_records() -> list[dict]:
    return load_consolidated_records()


@router.get("/summary")
def synthetic_summary() -> dict:
    return summarize_consolidated_records(load_consolidated_records())


@router.get("/uploaded-records")
def list_uploaded_records() -> list[dict]:
    return load_uploaded_records()


@router.get("/uploaded-summary")
def uploaded_summary() -> dict:
    return summarize_consolidated_records(load_uploaded_records())
