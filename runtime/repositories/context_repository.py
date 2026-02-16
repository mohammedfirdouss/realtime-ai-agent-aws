"""Repository for Context records in DynamoDB.

Context table schema:
    PK: AGENT#<agentId>   SK: CONTEXT#<timestamp>
TTL attribute: TTL (epoch seconds)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from runtime.shared.constants import PK_AGENT

from .base_repository import BaseRepository

# Default context TTL: 7 days
DEFAULT_CONTEXT_TTL_SECONDS = 7 * 24 * 60 * 60

SK_CONTEXT_PREFIX = "CONTEXT#"


class ContextRepository(BaseRepository):
    """Append-oriented operations for conversation context records."""

    # ------------------------------------------------------------------
    # Create / Append
    # ------------------------------------------------------------------

    def put_context(
        self,
        *,
        agent_id: str,
        conversation_history: list[dict[str, Any]],
        agent_memory: dict[str, Any] | None = None,
        task_state: dict[str, Any] | None = None,
        ttl_seconds: int = DEFAULT_CONTEXT_TTL_SECONDS,
    ) -> dict[str, Any]:
        """Store a new context snapshot.

        Each call creates a new record keyed by the current timestamp,
        enabling an append-only log of context versions. TTL ensures
        old snapshots expire automatically.
        """
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        ttl_epoch = int(time.time()) + ttl_seconds

        item: dict[str, Any] = {
            "PK": f"{PK_AGENT}{agent_id}",
            "SK": f"{SK_CONTEXT_PREFIX}{timestamp}",
            "agentId": agent_id,
            "conversationHistory": conversation_history,
            "agentMemory": agent_memory or {},
            "taskState": task_state or {},
            "timestamp": timestamp,
            "TTL": ttl_epoch,
        }
        self.put_item(item)
        return item

    def append_messages(
        self,
        agent_id: str,
        messages: list[dict[str, Any]],
        *,
        ttl_seconds: int = DEFAULT_CONTEXT_TTL_SECONDS,
    ) -> dict[str, Any]:
        """Append new messages to the agent's context.

        Loads the latest context, extends the conversation history
        with the new messages, and writes a new snapshot.
        """
        latest = self.get_latest_context(agent_id)
        history: list[dict[str, Any]] = []
        agent_memory: dict[str, Any] = {}
        task_state: dict[str, Any] = {}

        if latest:
            history = list(latest.get("conversationHistory", []))
            agent_memory = dict(latest.get("agentMemory", {}))
            task_state = dict(latest.get("taskState", {}))

        history.extend(messages)

        return self.put_context(
            agent_id=agent_id,
            conversation_history=history,
            agent_memory=agent_memory,
            task_state=task_state,
            ttl_seconds=ttl_seconds,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_latest_context(self, agent_id: str) -> dict[str, Any] | None:
        """Retrieve the most recent context snapshot for an agent."""
        items = self.query(
            f"{PK_AGENT}{agent_id}",
            sk_begins_with=SK_CONTEXT_PREFIX,
            scan_forward=False,
            limit=1,
        )
        return items[0] if items else None

    def list_context_history(
        self,
        agent_id: str,
        *,
        limit: int = 10,
        scan_forward: bool = False,
    ) -> list[dict[str, Any]]:
        """List recent context snapshots for an agent (newest first)."""
        return self.query(
            f"{PK_AGENT}{agent_id}",
            sk_begins_with=SK_CONTEXT_PREFIX,
            scan_forward=scan_forward,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_agent_context(self, agent_id: str) -> int:
        """Delete all context records for an agent. Returns count deleted."""
        items = self.query(
            f"{PK_AGENT}{agent_id}",
            sk_begins_with=SK_CONTEXT_PREFIX,
        )
        if items:
            keys = [(item["PK"], item["SK"]) for item in items]
            self.batch_delete(keys)
        return len(items)
