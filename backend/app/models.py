from pydantic import BaseModel, Field

from app.config import settings


class IndexRepoRequest(BaseModel):
    github_url: str = Field(
        ...,
        max_length=1000,
        description="Public GitHub repository URL to index",
        examples=["https://github.com/fastapi/fastapi"],
    )


class IndexRepoResponse(BaseModel):
    task_id: str
    session_id: str
    message: str
    github_url: str
    csrf_token: str | None = None


class IndexStatusResponse(BaseModel):
    status: str
    task_id: str
    stage: str | None = None
    detail: str | None = None
    session_id: str | None = None
    github_url: str | None = None


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Active session ID from indexed repo")
    message: str = Field(
        ..., max_length=settings.max_chat_message_length, description="User prompt or architectural question"
    )


class ClearSessionRequest(BaseModel):
    session_id: str = Field(..., description="Active session ID to clear")


class FileContentResponse(BaseModel):
    content: str
    file_path: str


class TreeItem(BaseModel):
    name: str
    path: str
    is_dir: bool


class SymbolContentResponse(BaseModel):
    content: str
    symbol: str


class CleanupResponse(BaseModel):
    status: str
    deleted_sessions: list[str]
    freed_bytes: int
    remaining_sessions_count: int
    remaining_bytes: int
