"""API Key authorizer Lambda function for API Gateway.

Validates incoming API keys against a set of valid keys stored
in AWS Secrets Manager.  Returns an IAM policy document that
API Gateway uses to allow or deny the request.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from runtime.shared.constants import (
    AUTH_HEADER_API_KEY,
    ROLE_USER,
    VALID_ROLES,
)
from runtime.shared.secrets import get_secret

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda authorizer entry-point for API-key authentication.

    The function expects the API key in the ``x-api-key`` header (or
    ``authorizationToken`` when using a TOKEN authorizer).

    Environment variables consumed:
        API_KEYS_SECRET_NAME – Secrets Manager name that stores a JSON
            mapping of ``{ "<api-key-hash>": { "user_id": "…", "role": "…" } }``.
    """
    import os

    secret_name = os.environ.get("API_KEYS_SECRET_NAME", "")
    if not secret_name:
        logger.error("API_KEYS_SECRET_NAME environment variable not set")
        return _deny_policy(event)

    api_key = _extract_api_key(event)
    if not api_key:
        logger.warning("Missing API key in request")
        return _deny_policy(event)

    try:
        keys_json = get_secret(secret_name)
        valid_keys: dict[str, Any] = json.loads(keys_json)
    except Exception:
        logger.exception("Failed to retrieve API keys secret")
        return _deny_policy(event)

    key_hash = _hash_key(api_key)
    key_entry = valid_keys.get(key_hash)
    if key_entry is None:
        logger.warning("Invalid API key provided")
        return _deny_policy(event)

    user_id: str = key_entry.get("user_id", "unknown")
    role: str = key_entry.get("role", ROLE_USER)
    if role not in VALID_ROLES:
        role = ROLE_USER

    return _allow_policy(
        event,
        principal_id=user_id,
        context={"user_id": user_id, "role": role, "auth_type": "api_key"},
    )
# Helpers
def _extract_api_key(event: dict[str, Any]) -> str | None:
    """Extract the API key from various event formats."""
    # TOKEN authorizer: key is in authorizationToken
    token = event.get("authorizationToken")
    if token:
        return token.strip()

    # REQUEST authorizer: key may be in headers
    headers = event.get("headers") or {}
    # Headers may be mixed-case
    for header_name, header_value in headers.items():
        if header_name.lower() == AUTH_HEADER_API_KEY:
            return header_value.strip()

    return None
def _hash_key(api_key: str) -> str:
    """Produce a deterministic SHA-256 hex digest for an API key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
def _extract_method_arn(event: dict[str, Any]) -> str:
    """Return the methodArn from the event, with a safe fallback."""
    return event.get("methodArn", "arn:aws:execute-api:*:*:*/*/*/*")
def _allow_policy(
    event: dict[str, Any],
    *,
    principal_id: str,
    context: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an API Gateway *Allow* policy document."""
    policy: dict[str, Any] = {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": _extract_method_arn(event),
                }
            ],
        },
    }
    if context:
        policy["context"] = context
    return policy
def _deny_policy(event: dict[str, Any]) -> dict[str, Any]:
    """Build an API Gateway *Deny* policy document."""
    return {
        "principalId": "anonymous",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Deny",
                    "Resource": _extract_method_arn(event),
                }
            ],
        },
    }
def validate_api_key(
    api_key: str,
    valid_keys: dict[str, Any],
) -> dict[str, Any] | None:
    """Validate an API key against a mapping of hashed keys.

    Returns the key metadata dict on success, ``None`` on failure.
    This is a pure function suitable for direct unit testing.
    """
    if not api_key:
        return None
    key_hash = _hash_key(api_key)
    return valid_keys.get(key_hash)
