"""Authorization middleware for Lambda handlers.

Provides a ``require_permission`` decorator that checks whether the
caller (identified via API Gateway authorizer context) has the
required permission.  Supports role-based access control and
optional resource-level ownership checks.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

from runtime.shared.constants import (
    PERM_ADMIN_ALL,
    ROLE_ADMIN,
    ROLE_PERMISSIONS,
    VALID_PERMISSIONS,
    VALID_ROLES,
)

logger = logging.getLogger(__name__)

# Type alias for a Lambda handler function.
HandlerFunc = Callable[[dict[str, Any], Any], dict[str, Any]]


# ------------------------------------------------------------------
# Permission checking
# ------------------------------------------------------------------


def has_permission(role: str, permission: str) -> bool:
    """Return ``True`` if *role* grants *permission*.

    Admin users match the wildcard ``admin:*`` permission and therefore
    pass every check.
    """
    if role not in VALID_ROLES:
        return False
    if permission not in VALID_PERMISSIONS:
        return False
    role_perms = ROLE_PERMISSIONS.get(role, frozenset())
    return permission in role_perms or PERM_ADMIN_ALL in role_perms


def check_resource_access(
    role: str,
    user_id: str,
    resource_owner_id: str | None,
) -> bool:
    """Check whether *user_id* may access a resource owned by *resource_owner_id*.

    Admins can access any resource.  Regular users can only access their
    own resources.  If *resource_owner_id* is ``None`` the check is
    skipped (the resource has no owner concept).
    """
    if role == ROLE_ADMIN:
        return True
    if resource_owner_id is None:
        return True
    return user_id == resource_owner_id


# ------------------------------------------------------------------
# Decorator
# ------------------------------------------------------------------


def require_permission(
    permission: str,
    *,
    resource_owner_field: str | None = None,
) -> Callable[[HandlerFunc], HandlerFunc]:
    """Decorator that enforces *permission* before invoking the handler.

    Usage::

        @require_permission("agent:create")
        def handler(event, context):
            ...

    The caller identity is read from
    ``event["requestContext"]["authorizer"]`` which API Gateway populates
    from the authorizer Lambda response context.

    Args:
        permission: The permission string to check (e.g. ``"agent:read"``).
        resource_owner_field: Optional key path in the *event body* that
            holds the resource owner user-id.  When supplied, a resource-level
            ownership check is also performed.
    """
    if permission not in VALID_PERMISSIONS:
        raise ValueError(f"Unknown permission: {permission}")

    def decorator(func: HandlerFunc) -> HandlerFunc:
        @functools.wraps(func)
        def wrapper(event: dict[str, Any], context: Any) -> dict[str, Any]:
            auth_context = _extract_auth_context(event)

            role = auth_context.get("role", "")
            user_id = auth_context.get("user_id", "")

            if not role or not user_id:
                logger.warning("Missing auth context in request")
                return _forbidden_response("Authentication required")

            if not has_permission(role, permission):
                logger.warning(
                    "Permission denied: user=%s role=%s permission=%s",
                    user_id,
                    role,
                    permission,
                )
                return _forbidden_response("Insufficient permissions")

            # Optional resource-level ownership check
            if resource_owner_field is not None:
                owner_id = _extract_resource_owner(event, resource_owner_field)
                if not check_resource_access(role, user_id, owner_id):
                    logger.warning(
                        "Resource access denied: user=%s owner=%s",
                        user_id,
                        owner_id,
                    )
                    return _forbidden_response("Access denied to this resource")

            return func(event, context)

        return wrapper

    return decorator


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_auth_context(event: dict[str, Any]) -> dict[str, str]:
    """Pull authorizer context from the API Gateway event."""
    request_context = event.get("requestContext") or {}
    authorizer = request_context.get("authorizer") or {}
    return {
        "user_id": str(authorizer.get("user_id", "")),
        "role": str(authorizer.get("role", "")),
        "auth_type": str(authorizer.get("auth_type", "")),
    }


def _extract_resource_owner(event: dict[str, Any], field: str) -> str | None:
    """Extract the resource owner id from the event body or path params."""
    # Try path parameters first
    path_params = event.get("pathParameters") or {}
    if field in path_params:
        return str(path_params[field])

    # Try JSON body
    body = event.get("body")
    if isinstance(body, str):
        try:
            import json

            body = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(body, dict):
        value = body.get(field)
        if value is not None:
            return str(value)

    return None


def _forbidden_response(message: str) -> dict[str, Any]:
    """Return a 403 Forbidden API Gateway proxy response."""
    import json

    return {
        "statusCode": 403,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"message": message}),
    }
