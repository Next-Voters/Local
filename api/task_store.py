"""Redis-backed task storage for NV Local background jobs.

This module provides task state management for background processing using
Redis as the storage backend. It handles creating, retrieving, and updating
task status.

Classes:
    TaskData: Data class holding task metadata and results.
    RedisTaskStore: Interface for Redis-based task CRUD operations.

The module exposes a singleton task_store instance for use by the API.
"""

import json
import os
import uuid
from typing import Any

import redis

from api.models import TaskStatus


class TaskData:
    def __init__(
        self,
        task_id: str,
        status: str,
        result: str | None = None,
        error: str | None = None,
    ):
        self.task_id = task_id
        self.status = status
        self.result = result
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskData":
        return cls(
            task_id=data["task_id"],
            status=data["status"],
            result=data.get("result"),
            error=data.get("error"),
        )


class RedisTaskStore:
    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self.key_prefix = "nvlocal:task:"
        self.ttl_seconds = int(os.getenv("TASK_TTL_SECONDS", "86400"))

    @property
    def redis(self):
        return self._redis

    def _get_key(self, task_id: str) -> str:
        return f"{self.key_prefix}{task_id}"

    def create_task(self, city: str) -> TaskData:
        task_id = str(uuid.uuid4())
        task = TaskData(task_id=task_id, status=TaskStatus.PENDING)
        self.redis.set(
            self._get_key(task_id), json.dumps(task.to_dict()), ex=self.ttl_seconds
        )
        return task

    def get_task(self, task_id: str) -> TaskData | None:
        data = self.redis.get(self._get_key(task_id))
        if data is None:
            return None
        return TaskData.from_dict(json.loads(data))

    def update_task(
        self,
        task_id: str,
        status: str,
        result: str | None = None,
        error: str | None = None,
    ) -> TaskData:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        task.status = status
        task.result = result
        task.error = error

        self.redis.set(self._get_key(task_id), json.dumps(task.to_dict()))
        return task


task_store = RedisTaskStore()
