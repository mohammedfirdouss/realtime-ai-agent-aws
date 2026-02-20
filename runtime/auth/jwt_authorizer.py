"""JWT authorizer Lambda function for API Gateway.

Validates incoming JWT bearer tokens and extracts user identity
and role information.  The signing secret is stored in AWS Secrets
Manager.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any

from runtime.shared.constants import (
    AUTH_BEARER_PREFIX,
    AUTH_HEADER_AUTHORIZATION,
    ROLE_USER,
    VALID_ROLES,
)
from runtime.shared.secrets import get_secret

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda authorizer entry-point for JWT authentication.

    Environment variables consumed:
        JWT_SECRET_NAME – Secrets Manager name that holds the signing key.
        JWT_ALGORITHM   – (optional) Currently only ``HS256`` is supported.
    """
    import os

    secret_name = os.environ.get("JWT_SECRET_NAME", "")
    if not secret_name:
        logger.error("JWT_SECRET_NAME environment variable not set")
        return _deny_policy(event)

    token = _extract_bearer_token(event)
    if not token:
        logger.warning("Missing or malformed Authorization header")
        return _deny_policy(event)

    try:
        signing_key = get_secret(secret_name)
    except Exception:
        logger.exception("Failed to retrieve JWT signing secret")
        return _deny_policy(event)

    claims = decode_jwt(token, signing_key)
    if claims is None:
        logger.warning("JWT validation failed")
        return _deny_policy(event)

    identity = extract_user_identity(claims)

    return _allow_policy(
        event,
        principal_id=identity["user_id"],
        context={
            "user_id": identity["user_id"],
            "role": identity["role"],
            "auth_type": "jwt",
        },
    )
# Token extraction
def _extract_bearer_token(event: dict[str, Any]) -> str | None:
    """Extract the JWT from the Authorization header."""
    # TOKEN authorizer: token is in authorizationToken
    token = event.get("authorizationToken")
    if token and token.startswith(AUTH_BEARER_PREFIX):
        return token[len(AUTH_BEARER_PREFIX) :].strip()

    # REQUEST authorizer: check headers
    headers = event.get("headers") or {}
    for header_name, header_value in headers.items():
        if header_name.lower() == AUTH_HEADER_AUTHORIZATION.lower():
            if header_value.startswith(AUTH_BEARER_PREFIX):
                return header_value[len(AUTH_BEARER_PREFIX) :].strip()

    return None
# Minimal HS256 JWT implementation (no external dependencies)
def _b64url_encode(data: bytes) -> str:
    """Base64url-encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
def _b64url_decode(s: str) -> bytes:
    """Base64url-decode, re-adding padding as needed."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)
def decode_jwt(token: str, signing_key: str) -> dict[str, Any] | None:
    """Decode and validate an HS256 JWT token.

    Returns the payload claims on success, ``None`` on failure.
    Checks: structure, signature, ``exp`` claim.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None

    try:
        header_b64, payload_b64, signature_b64 = parts
        header = json.loads(_b64url_decode(header_b64))
    except Exception:
        return None

    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        return None

    # Verify signature
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(
        signing_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()

    try:
        actual_sig = _b64url_decode(signature_b64)
    except Exception:
        return None

    if not hmac.compare_digest(expected_sig, actual_sig):
        return None

    # Decode payload
    try:
        payload: dict[str, Any] = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return None

    # Check expiration
    exp = payload.get("exp")
    if exp is not None:
        try:
            if float(exp) < time.time():
                return None
        except (TypeError, ValueError):
            return None

    return payload
def create_jwt(payload: dict[str, Any], signing_key: str) -> str:
    """Create an HS256 JWT token (useful for testing).

    The payload should include ``sub``, ``role``, and optionally ``exp``.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(
        signing_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"
def extract_user_identity(claims: dict[str, Any]) -> dict[str, str]:
    """Extract user identity fields from validated JWT claims.

    Returns a dict with ``user_id`` and ``role`` suitable for
    passing to downstream handlers via the authorizer context.
    """
    user_id = claims.get("sub", "unknown")
    role = claims.get("role", ROLE_USER)
    if role not in VALID_ROLES:
        role = ROLE_USER
    return {"user_id": str(user_id), "role": role}
# Policy helpers (shared shape with api_key_authorizer)
def _extract_method_arn(event: dict[str, Any]) -> str:
    return event.get("methodArn", "arn:aws:execute-api:*:*:*/*/*/*")
def _allow_policy(
    event: dict[str, Any],
    *,
    principal_id: str,
    context: dict[str, str] | None = None,
) -> dict[str, Any]:
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
