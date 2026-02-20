"""Repository for WebSocket Connection records in DynamoDB.

Connections table schema:
    PK: CONNECTION#<connectionId>   SK: METADATA
TTL attribute: TTL (epoch seconds)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from runtime.shared.constants import PK_CONNECTION, SK_METADATA

from .base_repository import BaseRepository

# Default connection TTL: 2 hours
DEFAULT_CONNECTION_TTL_SECONDS = 2 * 60 * 60
class ConnectionRepository(BaseRepository):
    """CRUD operations for WebSocket connection records."""

    # Create

    def create_connection(
        self,
        *,
        connection_id: str,
        user_id: str,
        ttl_seconds: int = DEFAULT_CONNECTION_TTL_SECONDS,
    ) -> dict[str, Any]:
        """Register a new WebSocket connection."""
        now = datetime.now(timezone.utc).isoformat()
        ttl_epoch = int(time.time()) + ttl_seconds

        item: dict[str, Any] = {
            "PK": f"{PK_CONNECTION}{connection_id}",
            "SK": SK_METADATA,
            "connectionId": connection_id,
            "userId": user_id,
            "subscriptions": [],
            "connectedAt": now,
            "TTL": ttl_epoch,
        }
        self.put_item(item)
        return item

    # Read

    def get_connection(self, connection_id: str) -> dict[str, Any]:
        """Get a connection record. Raises ItemNotFoundError if missing."""
        return self.get_item(f"{PK_CONNECTION}{connection_id}", SK_METADATA)

    def get_connection_or_none(self, connection_id: str) -> dict[str, Any] | None:
        """Get a connection, returning None if not found."""
        return self.get_item_or_none(f"{PK_CONNECTION}{connection_id}", SK_METADATA)

    # Subscription management

    def add_subscription(self, connection_id: str, agent_id: str) -> dict[str, Any]:
        """Subscribe a connection to an agent's updates.

        Uses a conditional update to avoid duplicate subscriptions.
        """
        conn = self.get_connection(connection_id)
        subs: list[str] = conn.get("subscriptions", [])
        if agent_id in subs:
            return conn

        new_subs = subs + [agent_id]
        return self.update_item(
            f"{PK_CONNECTION}{connection_id}",
            SK_METADATA,
            update_expression="SET subscriptions = :subs",
            expression_attribute_values={
                ":subs": new_subs,
                ":expected_subs": subs,
            },
            condition_expression="attribute_exists(PK) AND subscriptions = :expected_subs",
        )

    def remove_subscription(
        self, connection_id: str, agent_id: str
    ) -> dict[str, Any]:
        """Remove an agent subscription from a connection.

        Loads the current list, filters out the agent_id, and writes back.
        """
        conn = self.get_connection(connection_id)
        subs: list[str] = conn.get("subscriptions", [])
        if agent_id not in subs:
            return conn
        new_subs = [s for s in subs if s != agent_id]

        return self.update_item(
            f"{PK_CONNECTION}{connection_id}",
            SK_METADATA,
            update_expression="SET subscriptions = :subs",
            expression_attribute_values={
                ":subs": new_subs,
                ":expected_subs": subs,
            },
            condition_expression="attribute_exists(PK) AND subscriptions = :expected_subs",
        )

    def get_subscriptions(self, connection_id: str) -> list[str]:
        """Get list of agent IDs this connection is subscribed to."""
        conn = self.get_connection(connection_id)
        return conn.get("subscriptions", [])

    # Delete

    def delete_connection(self, connection_id: str) -> None:
        """Remove a connection record (on disconnect)."""
        self.delete_item(f"{PK_CONNECTION}{connection_id}", SK_METADATA)

    # Query helpers

    def get_connections_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """Get all active connections for a user.

        Note: This requires a table scan filtered by userId.
        For high-volume production use, consider adding a GSI on userId.
        """
        response = self._table.scan(
            FilterExpression="userId = :uid",
            ExpressionAttributeValues={":uid": user_id},
        )
        return response.get("Items", [])
