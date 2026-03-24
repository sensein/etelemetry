"""Health-check route."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health() -> dict:
    """Return basic service information."""
    return {"name": "etelemetry", "version": "2.0.0"}
