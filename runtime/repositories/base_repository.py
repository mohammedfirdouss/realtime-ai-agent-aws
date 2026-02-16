"""Base repository with common DynamoDB operations.

All concrete repositories inherit from this class to get consistent
put/get/update/delete/query behaviour and error handling.
"""

from __future__ import annotations

import logging
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class ItemNotFoundError(Exception):
    """Raised when a requested item does not exist."""


class ConditionalCheckError(Exception):
    """Raised when a conditional write fails (e.g. item already exists)."""


class BaseRepository:
    """Thin wrapper around a single DynamoDB table resource."""

    def __init__(
        self,
        table_name: str,
        *,
        region: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if region:
            kwargs["region_name"] = region
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url

        self._resource = boto3.resource("dynamodb", **kwargs)
        self._table = self._resource.Table(table_name)
        self._table_name = table_name

    @property
    def table_name(self) -> str:
        return self._table_name

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def put_item(
        self,
        item: dict[str, Any],
        *,
        condition_expression: str | None = None,
        expression_attribute_names: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Put an item into the table.

        Returns the item as stored.
        Raises ConditionalCheckError if condition_expression fails.
        """
        kwargs: dict[str, Any] = {"Item": item}
        if condition_expression:
            kwargs["ConditionExpression"] = condition_expression
        if expression_attribute_names:
            kwargs["ExpressionAttributeNames"] = expression_attribute_names

        try:
            self._table.put_item(**kwargs)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ConditionalCheckError(
                    f"Conditional check failed for {item.get('PK')}/{item.get('SK')}"
                ) from exc
            raise
        return item

    def get_item(self, pk: str, sk: str) -> dict[str, Any]:
        """Get a single item by its composite key.

        Raises ItemNotFoundError if the item does not exist.
        """
        response = self._table.get_item(Key={"PK": pk, "SK": sk})
        item = response.get("Item")
        if item is None:
            raise ItemNotFoundError(f"Item not found: PK={pk}, SK={sk}")
        return item

    def get_item_or_none(self, pk: str, sk: str) -> dict[str, Any] | None:
        """Get a single item by its composite key, returning None if missing."""
        response = self._table.get_item(Key={"PK": pk, "SK": sk})
        return response.get("Item")

    def delete_item(
        self,
        pk: str,
        sk: str,
        *,
        condition_expression: str | None = None,
    ) -> None:
        """Delete an item by its composite key."""
        kwargs: dict[str, Any] = {"Key": {"PK": pk, "SK": sk}}
        if condition_expression:
            kwargs["ConditionExpression"] = condition_expression

        try:
            self._table.delete_item(**kwargs)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ConditionalCheckError(
                    f"Conditional check failed for delete: PK={pk}, SK={sk}"
                ) from exc
            raise

    def update_item(
        self,
        pk: str,
        sk: str,
        *,
        update_expression: str,
        expression_attribute_values: dict[str, Any],
        expression_attribute_names: dict[str, str] | None = None,
        condition_expression: str | None = None,
    ) -> dict[str, Any]:
        """Update an item and return all new attributes."""
        kwargs: dict[str, Any] = {
            "Key": {"PK": pk, "SK": sk},
            "UpdateExpression": update_expression,
            "ExpressionAttributeValues": expression_attribute_values,
            "ReturnValues": "ALL_NEW",
        }
        if expression_attribute_names:
            kwargs["ExpressionAttributeNames"] = expression_attribute_names
        if condition_expression:
            kwargs["ConditionExpression"] = condition_expression

        try:
            response = self._table.update_item(**kwargs)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ConditionalCheckError(
                    f"Conditional check failed for update: PK={pk}, SK={sk}"
                ) from exc
            raise
        return response.get("Attributes", {})

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def query(
        self,
        pk_value: str,
        *,
        sk_begins_with: str | None = None,
        sk_between: tuple[str, str] | None = None,
        scan_forward: bool = True,
        limit: int | None = None,
        index_name: str | None = None,
        pk_name: str = "PK",
        sk_name: str = "SK",
    ) -> list[dict[str, Any]]:
        """Query items by partition key with optional sort key conditions.

        Returns a list of items (may be empty).
        """
        key_condition = Key(pk_name).eq(pk_value)
        if sk_begins_with:
            key_condition = key_condition & Key(sk_name).begins_with(sk_begins_with)
        elif sk_between:
            key_condition = key_condition & Key(sk_name).between(*sk_between)

        kwargs: dict[str, Any] = {
            "KeyConditionExpression": key_condition,
            "ScanIndexForward": scan_forward,
        }
        if limit:
            kwargs["Limit"] = limit
        if index_name:
            kwargs["IndexName"] = index_name

        items: list[dict[str, Any]] = []
        response = self._table.query(**kwargs)
        items.extend(response.get("Items", []))

        # Auto-paginate when no limit is specified
        while "LastEvaluatedKey" in response and limit is None:
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = self._table.query(**kwargs)
            items.extend(response.get("Items", []))

        return items

    def query_page(
        self,
        pk_value: str,
        *,
        sk_begins_with: str | None = None,
        limit: int = 25,
        scan_forward: bool = True,
        exclusive_start_key: dict[str, Any] | None = None,
        index_name: str | None = None,
        pk_name: str = "PK",
        sk_name: str = "SK",
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Query a single page of results with pagination support.

        Returns (items, last_evaluated_key). last_evaluated_key is None
        when there are no more pages.
        """
        key_condition = Key(pk_name).eq(pk_value)
        if sk_begins_with:
            key_condition = key_condition & Key(sk_name).begins_with(sk_begins_with)

        kwargs: dict[str, Any] = {
            "KeyConditionExpression": key_condition,
            "ScanIndexForward": scan_forward,
            "Limit": limit,
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key
        if index_name:
            kwargs["IndexName"] = index_name

        response = self._table.query(**kwargs)
        items = response.get("Items", [])
        last_key = response.get("LastEvaluatedKey")
        return items, last_key

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    def batch_write(self, items: list[dict[str, Any]]) -> None:
        """Write multiple items in a batch (max 25 per call)."""
        with self._table.batch_writer() as writer:
            for item in items:
                writer.put_item(Item=item)

    def batch_delete(self, keys: list[tuple[str, str]]) -> None:
        """Delete multiple items by key pairs (pk, sk)."""
        with self._table.batch_writer() as writer:
            for pk, sk in keys:
                writer.delete_item(Key={"PK": pk, "SK": sk})
