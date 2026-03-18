"""Pydantic models for NV Local API request and response schemas.

This module defines the data models used by the FastAPI server for handling
background task submissions and status queries.

Classes:
    TaskStatus: Enum representing task lifecycle states.
    BackgroundSubmitRequest: Request model for submitting a city analysis task.
    BackgroundSubmitResponse: Response model for task submission.
    BackgroundStatusResponse: Response model for task status queries.
"""

from enum import Enum
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BackgroundSubmitRequest(BaseModel):
    city: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z\s\-]+$")


class BackgroundSubmitResponse(BaseModel):
    task_id: str
    status: TaskStatus


class BackgroundStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    result: str | None = None
    error: str | None = None
