from fastapi import APIRouter

router = APIRouter(tags=["API"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "repotraverse-backend"}
