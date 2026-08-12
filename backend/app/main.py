from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.config import settings
from app.logger import logger
from app.redis_client import get_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"RepoTraverse Backend started successfully in '{settings.environment}' mode.")
    yield
    logger.info("RepoTraverse Backend service shutting down.")
    get_redis_client().close()


app = FastAPI(
    title="RepoTraverse",
    description="GitHub Repository Indexing & Architectural QA Agent",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS middleware using explicit allowed origins from environment settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

allowed_hosts = set()
for origin in settings.parsed_cors_origins:
    host = urlparse(origin).hostname
    if host:
        allowed_hosts.add(host)

# Always allow internal Docker container communication
allowed_hosts.add("backend")

# Only allow localhost and test runner hosts in non-production environments
if not settings.is_production:
    allowed_hosts.update(["localhost", "127.0.0.1", "testserver"])

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(allowed_hosts),
)


app.include_router(api_router)
