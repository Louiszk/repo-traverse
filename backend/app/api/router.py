from fastapi import APIRouter, Depends

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.indexing import router as indexing_router
from app.api.repository import router as repository_router
from app.api.session import router as session_router
from app.rate_limit import check_daily_budget

api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(session_router)
api_router.include_router(repository_router)
api_router.include_router(indexing_router, dependencies=[Depends(check_daily_budget)])
api_router.include_router(chat_router, dependencies=[Depends(check_daily_budget)])
