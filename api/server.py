"""FastAPI server for NV Local background task processing.

This module provides a REST API for submitting city analysis tasks that run
in the background. Tasks are executed asynchronously using a ThreadPoolExecutor
and their status is tracked via Redis.

Key endpoints:
    POST /api/background/submit: Submit a new city analysis task.
    GET /api/background/{task_id}: Get task status and result.
    GET /health: Health check endpoint.

The server uses the task_store module for Redis-backed task state management.
"""

import os
from concurrent.futures import TimeoutError
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.models import (
    BackgroundSubmitRequest,
    BackgroundSubmitResponse,
    BackgroundStatusResponse,
    TaskStatus,
)
from api.task_store import task_store

load_dotenv()

TASK_TIMEOUT_SECONDS = int(os.getenv("TASK_TIMEOUT_SECONDS", "300"))


def sanitize_error(error: Exception) -> str:
    error_msg = str(error)
    return error_msg[:500]


def run_pipeline_task(task_id: str, city: str):
    """Execute the pipeline in a background thread and update task status."""
    try:
        task_store.update_task(task_id, TaskStatus.PROCESSING)

        from pipelines.nv_local import run_pipeline

        result = run_pipeline(city)

        task_store.update_task(task_id, TaskStatus.COMPLETED, result=result)
    except TimeoutError:
        task_store.update_task(task_id, TaskStatus.FAILED, error="Task timed out")
    except Exception as e:
        task_store.update_task(task_id, TaskStatus.FAILED, error=sanitize_error(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="NV Local API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if os.getenv("DEBUG") == "true" else None,
        },
    )


@app.post("/api/background/submit", response_model=BackgroundSubmitResponse)
async def submit_background_task(
    request: BackgroundSubmitRequest, background_tasks: BackgroundTasks
):
    """Submit a new background task to process a city."""
    task = task_store.create_task(request.city)

    background_tasks.add_task(run_pipeline_task, task.task_id, request.city)

    return BackgroundSubmitResponse(task_id=task.task_id, status=task.status)


@app.get("/api/background/{task_id}", response_model=BackgroundStatusResponse)
async def get_task_status(task_id: str):
    """Get the current status of a background task."""
    task = task_store.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return BackgroundStatusResponse(
        task_id=task.task_id,
        status=task.status,
        result=task.result,
        error=task.error,
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        task_store.redis.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "redis": "disconnected"},
        )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
