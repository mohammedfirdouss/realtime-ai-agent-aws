"""Unit tests for the authorization middleware."""

from __future__ import annotations

import json
from typing import Any

import pytest

from runtime.auth.middleware import (
    _forbidden_response,
    check_resource_access,
    has_permission,
    require_permission,
)
from runtime.shared.constants import (
    PERM_ADMIN_ALL,
    PERM_AGENT_CREATE,
    PERM_AGENT_DELETE,
    PERM_AGENT_READ,
    PERM_TASK_CREATE,
    PERM_TASK_READ,
    ROLE_ADMIN,
    ROLE_SERVICE,
    ROLE_USER,
)


class TestHasPermission:
    def test_admin_has_all_permissions(self) -> None:
        assert has_permission(ROLE_ADMIN, PERM_AGENT_CREATE)
        assert has_permission(ROLE_ADMIN, PERM_ADMIN_ALL)
        assert has_permission(ROLE_ADMIN, PERM_TASK_CREATE)

    def test_user_has_crud_permissions(self) -> None:
        assert has_permission(ROLE_USER, PERM_AGENT_CREATE)
        assert has_permission(ROLE_USER, PERM_AGENT_READ)
        assert has_permission(ROLE_USER, PERM_TASK_CREATE)

    def test_user_cannot_admin(self) -> None:
        # Users don't have admin:* wildcard (but they have individual perms)
        # Actually, admin:* is only in admin's perms
        assert not has_permission(ROLE_USER, PERM_ADMIN_ALL)

    def test_service_limited_permissions(self) -> None:
        assert has_permission(ROLE_SERVICE, PERM_AGENT_READ)
        assert has_permission(ROLE_SERVICE, PERM_TASK_CREATE)
        assert has_permission(ROLE_SERVICE, PERM_TASK_READ)
        assert not has_permission(ROLE_SERVICE, PERM_AGENT_CREATE)
        assert not has_permission(ROLE_SERVICE, PERM_AGENT_DELETE)

    def test_unknown_role_denied(self) -> None:
        assert not has_permission("unknown-role", PERM_AGENT_READ)

    def test_unknown_permission_denied(self) -> None:
        assert not has_permission(ROLE_ADMIN, "unknown:permission")


class TestCheckResourceAccess:
    def test_admin_accesses_any_resource(self) -> None:
        assert check_resource_access(ROLE_ADMIN, "user-1", "user-2")

    def test_user_accesses_own_resource(self) -> None:
        assert check_resource_access(ROLE_USER, "user-1", "user-1")

    def test_user_denied_other_resource(self) -> None:
        assert not check_resource_access(ROLE_USER, "user-1", "user-2")

    def test_none_owner_always_allowed(self) -> None:
        assert check_resource_access(ROLE_USER, "user-1", None)
        assert check_resource_access(ROLE_SERVICE, "svc-1", None)


class TestRequirePermissionDecorator:
    def _make_event(
        self, user_id: str, role: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "requestContext": {
                "authorizer": {
                    "user_id": user_id,
                    "role": role,
                    "auth_type": "jwt",
                }
            },
        }
        if body is not None:
            event["body"] = json.dumps(body)
        return event

    def test_allowed_call(self) -> None:
        @require_permission(PERM_AGENT_READ)
        def my_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
            return {"statusCode": 200}

        result = my_handler(self._make_event("user-1", ROLE_USER), None)
        assert result["statusCode"] == 200

    def test_denied_call(self) -> None:
        @require_permission(PERM_AGENT_CREATE)
        def my_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
            return {"statusCode": 200}

        result = my_handler(self._make_event("svc-1", ROLE_SERVICE), None)
        assert result["statusCode"] == 403

    def test_missing_auth_context(self) -> None:
        @require_permission(PERM_AGENT_READ)
        def my_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
            return {"statusCode": 200}

        result = my_handler({}, None)
        assert result["statusCode"] == 403

    def test_resource_owner_check_pass(self) -> None:
        @require_permission(PERM_AGENT_READ, resource_owner_field="user_id")
        def my_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
            return {"statusCode": 200}

        event = self._make_event("user-1", ROLE_USER, body={"user_id": "user-1"})
        result = my_handler(event, None)
        assert result["statusCode"] == 200

    def test_resource_owner_check_fail(self) -> None:
        @require_permission(PERM_AGENT_READ, resource_owner_field="user_id")
        def my_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
            return {"statusCode": 200}

        event = self._make_event("user-1", ROLE_USER, body={"user_id": "user-2"})
        result = my_handler(event, None)
        assert result["statusCode"] == 403

    def test_admin_bypasses_resource_owner_check(self) -> None:
        @require_permission(PERM_AGENT_READ, resource_owner_field="user_id")
        def my_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
            return {"statusCode": 200}

        event = self._make_event("admin-1", ROLE_ADMIN, body={"user_id": "user-2"})
        result = my_handler(event, None)
        assert result["statusCode"] == 200

    def test_path_parameter_owner_check(self) -> None:
        @require_permission(PERM_AGENT_READ, resource_owner_field="owner_id")
        def my_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
            return {"statusCode": 200}

        event = self._make_event("user-1", ROLE_USER)
        event["pathParameters"] = {"owner_id": "user-1"}
        result = my_handler(event, None)
        assert result["statusCode"] == 200

    def test_invalid_permission_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown permission"):

            @require_permission("invalid:perm")
            def my_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
                return {"statusCode": 200}


class TestForbiddenResponse:
    def test_structure(self) -> None:
        resp = _forbidden_response("test message")
        assert resp["statusCode"] == 403
        body = json.loads(resp["body"])
        assert body["message"] == "test message"
