"""Repository for Agent records in DynamoDB.

Agents table schema:
    PK: AGENT#<agentId>   SK: METADATA
GSI1 (UserAgentsIndex):
    GSI1PK: USER#<userId>  GSI1SK: AGENT#<createdAt>
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from runtime.shared.constants import (
    AGENT_STATUS_IDLE,
    PK_AGENT,
    PK_USER,
    SK_METADATA,
)

from .base_repository import BaseRepository, ItemNotFoundError


class AgentRepository(BaseRepository):
    """CRUD operations for Agent records."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_agent(
        self,
        *,
        user_id: str,
        name: str,
        configuration: dict[str, Any],
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new agent. Returns the stored item.

        Generates a unique agent_id if not provided.
        Raises ConditionalCheckError if agent_id already exists.
        """
        agent_id = agent_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        item: dict[str, Any] = {
            "PK": f"{PK_AGENT}{agent_id}",
            "SK": SK_METADATA,
            "agentId": agent_id,
            "userId": user_id,
            "name": name,
            "configuration": configuration,
            "status": AGENT_STATUS_IDLE,
            "createdAt": now,
            "updatedAt": now,
            # GSI1 attributes for user-based queries
            "GSI1PK": f"{PK_USER}{user_id}",
            "GSI1SK": f"{PK_AGENT}{now}",
        }

        self.put_item(
            item,
            condition_expression="attribute_not_exists(PK)",
        )
        return item

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        """Get an agent by ID. Raises ItemNotFoundError if not found."""
        return self.get_item(f"{PK_AGENT}{agent_id}", SK_METADATA)

    def get_agent_or_none(self, agent_id: str) -> dict[str, Any] | None:
        """Get an agent by ID, returning None if not found."""
        return self.get_item_or_none(f"{PK_AGENT}{agent_id}", SK_METADATA)

    def list_agents_by_user(
        self,
        user_id: str,
        *,
        limit: int = 25,
        scan_forward: bool = False,
        exclusive_start_key: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """List agents belonging to a user (newest first by default).

        Returns (items, last_evaluated_key) for pagination.
        """
        return self.query_page(
            f"{PK_USER}{user_id}",
            sk_begins_with=PK_AGENT,
            limit=limit,
            scan_forward=scan_forward,
            exclusive_start_key=exclusive_start_key,
            index_name="UserAgentsIndex",
            pk_name="GSI1PK",
            sk_name="GSI1SK",
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_agent(
        self,
        agent_id: str,
        *,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Update agent fields. Returns the full updated item.

        Raises ItemNotFoundError if the agent does not exist.
        Allowed fields: name, configuration, status.
        """
        allowed_fields = {"name", "configuration", "status"}
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return self.get_agent(agent_id)

        now = datetime.now(timezone.utc).isoformat()
        filtered["updatedAt"] = now

        set_parts: list[str] = []
        attr_values: dict[str, Any] = {}
        attr_names: dict[str, str] = {}

        for idx, (key, value) in enumerate(filtered.items()):
            placeholder = f":v{idx}"
            alias = f"#f{idx}"
            set_parts.append(f"{alias} = {placeholder}")
            attr_values[placeholder] = value
            attr_names[alias] = key

        update_expr = "SET " + ", ".join(set_parts)

        return self.update_item(
            f"{PK_AGENT}{agent_id}",
            SK_METADATA,
            update_expression=update_expr,
            expression_attribute_values=attr_values,
            expression_attribute_names=attr_names,
            condition_expression="attribute_exists(PK)",
        )

    def update_agent_status(self, agent_id: str, status: str) -> dict[str, Any]:
        """Convenience method to update only the agent's status."""
        return self.update_agent(agent_id, updates={"status": status})

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_agent(self, agent_id: str) -> None:
        """Delete an agent. Raises ItemNotFoundError if not found."""
        # Verify existence first
        self.get_agent(agent_id)
        self.delete_item(f"{PK_AGENT}{agent_id}", SK_METADATA)
