"""EventBridge event publisher for the Realtime Agentic API.

Provides a typed interface for publishing domain events to
the custom EventBridge bus.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import boto3

from runtime.shared.config import RuntimeConfig
from runtime.shared.constants import (
    EVENT_AGENT_CREATED,
    EVENT_AGENT_DELETED,
    EVENT_ERROR_OCCURRED,
    EVENT_SCHEDULED_TASK,
    EVENT_SOURCE_AGENTS,
    EVENT_SOURCE_ERRORS,
    EVENT_SOURCE_SCHEDULER,
    EVENT_SOURCE_STATUS,
    EVENT_SOURCE_TASKS,
    EVENT_STATUS_CHANGED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_CREATED,
    EVENT_TASK_PROGRESS,
    VALID_AGENT_STATUSES,
    VALID_TASK_STATUSES,
)

logger = logging.getLogger(__name__)
class EventValidationError(Exception):
    """Raised when event data fails validation."""
class EventPublisher:
    """Publishes domain events to EventBridge.

    Each method corresponds to one of the event types defined in
    ``runtime.shared.constants``.
    """

    def __init__(self, config: RuntimeConfig) -> None:
        self._bus_name = config.event_bus_name
        kwargs: dict[str, Any] = {"region_name": config.aws_region}
        if config.eventbridge_endpoint:
            kwargs["endpoint_url"] = config.eventbridge_endpoint
        self._client = boto3.client("events", **kwargs)

    # Public helpers

    def publish_agent_created(
        self,
        agent_id: str,
        user_id: str,
        agent_name: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Publish an AgentCreated event.

        Returns:
            The EventBridge entry ID.
        """
        self._require("agent_id", agent_id)
        self._require("user_id", user_id)
        self._require("agent_name", agent_name)

        detail = {
            "agentId": agent_id,
            "userId": user_id,
            "agentName": agent_name,
        }
        if metadata:
            detail["metadata"] = metadata
        return self._put_event(EVENT_SOURCE_AGENTS, EVENT_AGENT_CREATED, detail)

    def publish_agent_deleted(
        self,
        agent_id: str,
        user_id: str,
    ) -> str:
        """Publish an AgentDeleted event."""
        self._require("agent_id", agent_id)
        self._require("user_id", user_id)

        detail = {"agentId": agent_id, "userId": user_id}
        return self._put_event(EVENT_SOURCE_AGENTS, EVENT_AGENT_DELETED, detail)

    def publish_task_created(
        self,
        task_id: str,
        agent_id: str,
        description: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Publish a TaskCreated event."""
        self._require("task_id", task_id)
        self._require("agent_id", agent_id)
        self._require("description", description)

        detail = {
            "taskId": task_id,
            "agentId": agent_id,
            "description": description,
        }
        if metadata:
            detail["metadata"] = metadata
        return self._put_event(EVENT_SOURCE_TASKS, EVENT_TASK_CREATED, detail)

    def publish_task_completed(
        self,
        task_id: str,
        agent_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> str:
        """Publish a TaskCompleted event."""
        self._require("task_id", task_id)
        self._require("agent_id", agent_id)
        if status not in VALID_TASK_STATUSES:
            raise EventValidationError(
                f"Invalid task status '{status}'. Must be one of {sorted(VALID_TASK_STATUSES)}"
            )

        detail: dict[str, Any] = {
            "taskId": task_id,
            "agentId": agent_id,
            "status": status,
        }
        if result is not None:
            detail["result"] = result
        return self._put_event(EVENT_SOURCE_TASKS, EVENT_TASK_COMPLETED, detail)

    def publish_task_progress(
        self,
        task_id: str,
        agent_id: str,
        progress_pct: int,
        *,
        message: str | None = None,
    ) -> str:
        """Publish a TaskProgress event."""
        self._require("task_id", task_id)
        self._require("agent_id", agent_id)
        if not 0 <= progress_pct <= 100:
            raise EventValidationError(
                f"progress_pct must be 0-100, got {progress_pct}"
            )

        detail: dict[str, Any] = {
            "taskId": task_id,
            "agentId": agent_id,
            "progressPct": progress_pct,
        }
        if message is not None:
            detail["message"] = message
        return self._put_event(EVENT_SOURCE_TASKS, EVENT_TASK_PROGRESS, detail)

    def publish_status_changed(
        self,
        agent_id: str,
        previous_status: str,
        new_status: str,
    ) -> str:
        """Publish an AgentStatusChanged event."""
        self._require("agent_id", agent_id)
        for label, value in [("previous_status", previous_status), ("new_status", new_status)]:
            if value not in VALID_AGENT_STATUSES:
                raise EventValidationError(
                    f"Invalid {label} '{value}'. "
                    f"Must be one of {sorted(VALID_AGENT_STATUSES)}"
                )

        detail = {
            "agentId": agent_id,
            "previousStatus": previous_status,
            "newStatus": new_status,
        }
        return self._put_event(EVENT_SOURCE_STATUS, EVENT_STATUS_CHANGED, detail)

    def publish_error_occurred(
        self,
        error_code: str,
        error_message: str,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Publish an ErrorOccurred event."""
        self._require("error_code", error_code)
        self._require("error_message", error_message)

        detail: dict[str, Any] = {
            "errorCode": error_code,
            "errorMessage": error_message,
        }
        if agent_id is not None:
            detail["agentId"] = agent_id
        if task_id is not None:
            detail["taskId"] = task_id
        if metadata:
            detail["metadata"] = metadata
        return self._put_event(EVENT_SOURCE_ERRORS, EVENT_ERROR_OCCURRED, detail)

    def publish_scheduled_task(
        self,
        task_id: str,
        agent_id: str,
        schedule_expression: str,
    ) -> str:
        """Publish a ScheduledTask event."""
        self._require("task_id", task_id)
        self._require("agent_id", agent_id)
        self._require("schedule_expression", schedule_expression)

        detail = {
            "taskId": task_id,
            "agentId": agent_id,
            "scheduleExpression": schedule_expression,
        }
        return self._put_event(EVENT_SOURCE_SCHEDULER, EVENT_SCHEDULED_TASK, detail)

    # Internal helpers

    @staticmethod
    def _require(name: str, value: str) -> None:
        if not value or not value.strip():
            raise EventValidationError(f"'{name}' must be a non-empty string")

    def _put_event(self, source: str, detail_type: str, detail: dict[str, Any]) -> str:
        """Send a single event entry to EventBridge and return the entry ID."""
        detail["timestamp"] = datetime.now(timezone.utc).isoformat()

        response = self._client.put_events(
            Entries=[
                {
                    "Source": source,
                    "DetailType": detail_type,
                    "Detail": json.dumps(detail),
                    "EventBusName": self._bus_name,
                }
            ]
        )

        failed = response.get("FailedEntryCount", 0)
        if failed:
            entries = response.get("Entries", [{}])
            error_code = entries[0].get("ErrorCode", "Unknown")
            error_msg = entries[0].get("ErrorMessage", "Unknown error")
            logger.error(
                "EventBridge put_events failed: %s - %s (source=%s, detail_type=%s)",
                error_code,
                error_msg,
                source,
                detail_type,
            )
            raise RuntimeError(
                f"Failed to publish event {detail_type}: {error_code} - {error_msg}"
            )

        entry_id: str = response["Entries"][0]["EventId"]
        logger.info(
            "Published event %s/%s (id=%s)",
            source,
            detail_type,
            entry_id,
        )
        return entry_id
