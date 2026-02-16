"""Secrets management utilities for Lambda functions.

Provides a cached interface to AWS Secrets Manager so that repeated
calls within the same Lambda invocation (or across warm starts) avoid
extra API calls.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_secret_cache: dict[str, str] = {}


def get_secret(secret_name: str, region: str | None = None) -> str:
    """Retrieve a plain-text secret from Secrets Manager (with in-memory cache).

    Args:
        secret_name: Full secret name or ARN.
        region: AWS region override.

    Returns:
        The secret string value.

    Raises:
        ClientError: If the secret cannot be retrieved.
    """
    if secret_name in _secret_cache:
        return _secret_cache[secret_name]

    client = boto3.client("secretsmanager", region_name=region)
    try:
        response = client.get_secret_value(SecretId=secret_name)
        value: str = response["SecretString"]
        _secret_cache[secret_name] = value
        return value
    except ClientError:
        logger.exception("Failed to retrieve secret: %s", secret_name)
        raise


def get_secret_json(secret_name: str, region: str | None = None) -> dict[str, Any]:
    """Retrieve a JSON-encoded secret and parse it.

    Args:
        secret_name: Full secret name or ARN.
        region: AWS region override.

    Returns:
        Parsed JSON object.
    """
    raw = get_secret(secret_name, region)
    return json.loads(raw)


def clear_cache() -> None:
    """Clear the in-memory secret cache (useful for testing)."""
    _secret_cache.clear()
