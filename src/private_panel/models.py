from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class JobKind(StrEnum):
    AUTO = "auto"
    DOUYIN_ACCOUNT_POSTS = "douyin_account_posts"
    DOUYIN_ACCOUNT_LIKED = "douyin_account_liked"
    DOUYIN_SINGLE = "douyin_single"
    DOUYIN_MIX = "douyin_mix"
    DOUYIN_FAVORITES = "douyin_favorites"
    TIKTOK_ACCOUNT_POSTS = "tiktok_account_posts"
    TIKTOK_ACCOUNT_LIKED = "tiktok_account_liked"
    TIKTOK_SINGLE = "tiktok_single"
    TIKTOK_MIX = "tiktok_mix"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PanelUser(BaseModel):
    id: str
    email: str = ""
    name: str = ""
    via: Literal["navi", "token"]


class JobCreate(BaseModel):
    kind: JobKind = JobKind.AUTO
    input_text: str = Field("", max_length=12000)


class JobRecord(BaseModel):
    id: str
    kind: JobKind
    status: JobStatus
    input_text: str
    platform: str = ""
    created_at: str
    started_at: str = ""
    finished_at: str = ""
    progress_total: int = 0
    progress_done: int = 0
    output_dir: str = ""
    log_tail: str = ""
    error: str = ""


class FileEntry(BaseModel):
    name: str
    relative_path: str
    size: int
    modified_at: str
