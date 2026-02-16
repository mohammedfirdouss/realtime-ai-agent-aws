"""Repository for Task records in DynamoDB.

Tasks table schema:
    PK: AGENT#<agentId>   SK: TASK#<taskId>
GSI1 (TaskStatusIndex):
    GSI1PK: TASK#<taskId>  GSI1SK: STATUS#<status>
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from runtime.shared.constants import PK_AGENT, PK_TASK, TASK_STATUS_PENDING

from .base_repository import BaseRepository, ItemNotFoundError


class TaskRepository(BaseRepository):
    """CRUD and query operations for Task records."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_task(
        self,
        *,
        agent_id: str,
        description: str,
        user_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new task for an agent. Returns the stored item."""
        task_id = task_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        item: dict[str, Any] = {
            "PK": f"{PK_AGENT}{agent_id}",
            "SK": f"{PK_TASK}{task_id}",
            "taskId": task_id,
            "agentId": agent_id,
            "description": description,
            "status": TASK_STATUS_PENDING,
            "currentStep": 0,
            "createdAt": now,
            # GSI1 attributes for task status queries
            "GSI1PK": f"{PK_TASK}{task_id}",
            "GSI1SK": f"STATUS#{TASK_STATUS_PENDING}",
        }
        if user_id:
            item["userId"] = user_id

        self.put_item(item, condition_expression="attribute_not_exists(PK) AND attribute_not_exists(SK)")
        return item

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_task(self, agent_id: str, task_id: str) -> dict[str, Any]:
        """Get a task by agent ID and task ID. Raises ItemNotFoundError."""
        return self.get_item(f"{PK_AGENT}{agent_id}", f"{PK_TASK}{task_id}")

    def get_task_or_none(self, agent_id: str, task_id: str) -> dict[str, Any] | None:
        """Get a task, returning None if not found."""
        return self.get_item_or_none(f"{PK_AGENT}{agent_id}", f"{PK_TASK}{task_id}")

    def list_tasks_by_agent(
        self,
        agent_id: str,
        *,
        limit: int = 25,
        scan_forward: bool = False,
        exclusive_start_key: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """List tasks for an agent, newest first by default."""
        return self.query_page(
            f"{PK_AGENT}{agent_id}",
            sk_begins_with=PK_TASK,
            limit=limit,
            scan_forward=scan_forward,
            exclusive_start_key=exclusive_start_key,
        )

    def get_task_by_id(self, task_id: str) -> dict[str, Any]:
        """Look up a task by task_id via GSI (TaskStatusIndex).

        Returns the first matching item. Raises ItemNotFoundError if not found.
        """
        items = self.query(
            f"{PK_TASK}{task_id}",
            limit=1,
            index_name="TaskStatusIndex",
            pk_name="GSI1PK",
            sk_name="GSI1SK",
        )
        if not items:
            raise ItemNotFoundError(f"Task not found: taskId={task_id}")
        return items[0]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_task_status(
        self,
        agent_id: str,
        task_id: str,
        status: str,
    ) -> dict[str, Any]:
        """Update the task status and GSI sort key."""
        now = datetime.now(timezone.utc).isoformat()
        update_parts = [
            "#st = :status",
            "GSI1SK = :gsi1sk",
            "updatedAt = :now",
        ]

        attr_values: dict[str, Any] = {
            ":status": status,
            ":gsi1sk": f"STATUS#{status}",
            ":now": now,
        }

        # Set completedAt when terminal state
        if status in ("completed", "failed", "cancelled"):
            update_parts.append("completedAt = :completed")
            attr_values[":completed"] = now

        return self.update_item(
            f"{PK_AGENT}{agent_id}",
            f"{PK_TASK}{task_id}",
            update_expression="SET " + ", ".join(update_parts),
            expression_attribute_values=attr_values,
            expression_attribute_names={"#st": "status"},
            condition_expression="attribute_exists(PK)",
        )

    def update_task_plan(
        self,
        agent_id: str,
        task_id: str,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Store or update the task plan."""
        now = datetime.now(timezone.utc).isoformat()
        return self.update_item(
            f"{PK_AGENT}{agent_id}",
            f"{PK_TASK}{task_id}",
            update_expression="SET #p = :plan, updatedAt = :now",
            expression_attribute_values={":plan": plan, ":now": now},
            expression_attribute_names={"#p": "plan"},
            condition_expression="attribute_exists(PK)",
        )

    def update_task_result(
        self,
        agent_id: str,
        task_id: str,
        result: Any,
    ) -> dict[str, Any]:
        """Store the task result."""
        now = datetime.now(timezone.utc).isoformat()
        return self.update_item(
            f"{PK_AGENT}{agent_id}",
            f"{PK_TASK}{task_id}",
            update_expression="SET #r = :result, updatedAt = :now",
            expression_attribute_values={":result": result, ":now": now},
            expression_attribute_names={"#r": "result"},
            condition_expression="attribute_exists(PK)",
        )

    def update_current_step(
        self,
        agent_id: str,
        task_id: str,
        step: int,
    ) -> dict[str, Any]:
        """Update the current step counter."""
        return self.update_item(
            f"{PK_AGENT}{agent_id}",
            f"{PK_TASK}{task_id}",
            update_expression="SET currentStep = :step",
            expression_attribute_values={":step": step},
            condition_expression="attribute_exists(PK)",
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_task(self, agent_id: str, task_id: str) -> None:
        """Delete a task."""
        self.delete_item(f"{PK_AGENT}{agent_id}", f"{PK_TASK}{task_id}")
