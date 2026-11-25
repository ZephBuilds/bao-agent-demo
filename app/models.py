from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    author: str
    content: str
    timestamp: datetime


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=160)
    owner: str | None = None
    due_date: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    source_message_id: str


class TaskReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[Task]
    messages_analyzed: int = Field(ge=0)
    extractor: str


class RunRequest(BaseModel):
    source: Literal["fixture", "discord"] = "fixture"
    extractor: Literal["rules", "anthropic"] = "rules"
    limit: int = Field(default=5, ge=1, le=50)
    channel_id: str | None = None
