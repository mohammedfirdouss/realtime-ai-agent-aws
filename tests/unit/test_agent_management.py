"""Unit tests for the Agent Management Lambda handler."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from runtime.handlers import agent_management as mod
from runtime.repositories.base_repository import ItemNotFoundError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module-level singletons between tests."""
    mod._config = None
    mod._repo = None
    mod._publisher = None
    yield
    mod._config = None
    mod._repo = None
    mod._publisher = None


@pytest.fixture()
def mock_env(monkeypatch: pytest.MonkeyPatch):
    """Set required environment variables."""
    monkeypatch.setenv("STAGE", "dev")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AGENTS_TABLE", "test-agents")
    monkeypatch.setenv("TASKS_TABLE", "test-tasks")
    monkeypatch.setenv("CONTEXT_TABLE", "test-context")
    monkeypatch.setenv("CONNECTIONS_TABLE", "test-connections")
    monkeypatch.setenv("EVENT_BUS_NAME", "test-bus")


def _api_event(
    method: str,
    body: dict[str, Any] | None = None,
    path_params: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    role: str = "user",
    user_id: str = "user-1",
) -> dict[str, Any]:
    """Build a minimal API Gateway proxy event."""
    event: dict[str, Any] = {
        "httpMethod": method,
        "pathParameters": path_params,
        "queryStringParameters": query_params,
        "requestContext": {
            "authorizer": {
                "role": role,
                "user_id": user_id,
            }
        },
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


# ---------------------------------------------------------------------------
# Tests: Routing
# ---------------------------------------------------------------------------


class TestRouting:
    """Test request routing logic."""

    @patch.object(mod, "_handle_create")
    def test_post_routes_to_create(self, mock_create: MagicMock):
        mock_create.return_value = {"statusCode": 201}
        event = _api_event("POST")
        result = mod.handler(event, None)
        assert result["statusCode"] == 201

    @patch.object(mod, "_handle_list")
    def test_get_without_id_routes_to_list(self, mock_list: MagicMock):
        mock_list.return_value = {"statusCode": 200}
        event = _api_event("GET")
        result = mod.handler(event, None)
        assert result["statusCode"] == 200

    @patch.object(mod, "_handle_get")
    def test_get_with_id_routes_to_get(self, mock_get: MagicMock):
        mock_get.return_value = {"statusCode": 200}
        event = _api_event("GET", path_params={"agentId": "a1"})
        result = mod.handler(event, None)
        assert result["statusCode"] == 200

    @patch.object(mod, "_handle_update")
    def test_put_routes_to_update(self, mock_update: MagicMock):
        mock_update.return_value = {"statusCode": 200}
        event = _api_event("PUT", path_params={"agentId": "a1"})
        result = mod.handler(event, None)
        assert result["statusCode"] == 200

    @patch.object(mod, "_handle_delete")
    def test_delete_routes_to_delete(self, mock_delete: MagicMock):
        mock_delete.return_value = {"statusCode": 204}
        event = _api_event("DELETE", path_params={"agentId": "a1"})
        result = mod.handler(event, None)
        assert result["statusCode"] == 204

    def test_unsupported_method_returns_405(self):
        event = _api_event("PATCH")
        result = mod.handler(event, None)
        assert result["statusCode"] == 405


# ---------------------------------------------------------------------------
# Tests: Create Agent
# ---------------------------------------------------------------------------


class TestCreateAgent:
    """Test agent creation handler."""

    @patch.object(mod, "_init")
    def test_create_agent_success(self, mock_init: MagicMock):
        repo = MagicMock()
        publisher = MagicMock()
        mock_init.return_value = (MagicMock(), repo, publisher)

        agent_item = {
            "PK": "AGENT#a1",
            "SK": "METADATA",
            "agentId": "a1",
            "userId": "user-1",
            "name": "TestAgent",
            "configuration": {},
            "status": "idle",
        }
        repo.create_agent.return_value = agent_item

        event = _api_event("POST", body={"name": "TestAgent"})
        result = mod._handle_create(event, None)

        assert result["statusCode"] == 201
        body = json.loads(result["body"])
        assert body["agentId"] == "a1"
        assert "PK" not in body
        assert "SK" not in body

        publisher.publish_agent_created.assert_called_once_with(
            agent_id="a1", user_id="user-1", agent_name="TestAgent"
        )

    @patch.object(mod, "_init")
    def test_create_agent_missing_body(self, mock_init: MagicMock):
        mock_init.return_value = (MagicMock(), MagicMock(), MagicMock())
        event = _api_event("POST")
        result = mod._handle_create(event, None)
        assert result["statusCode"] == 400

    @patch.object(mod, "_init")
    def test_create_agent_missing_name(self, mock_init: MagicMock):
        mock_init.return_value = (MagicMock(), MagicMock(), MagicMock())
        event = _api_event("POST", body={"configuration": {}})
        result = mod._handle_create(event, None)
        assert result["statusCode"] == 400

    @patch.object(mod, "_init")
    def test_create_agent_with_system_prompt_and_tools(self, mock_init: MagicMock):
        repo = MagicMock()
        publisher = MagicMock()
        mock_init.return_value = (MagicMock(), repo, publisher)

        repo.create_agent.return_value = {
            "agentId": "a2",
            "userId": "user-1",
            "name": "Bot",
            "configuration": {"system_prompt": "Hello", "tools": ["t1"]},
        }

        event = _api_event(
            "POST",
            body={"name": "Bot", "system_prompt": "Hello", "tools": ["t1"]},
        )
        result = mod._handle_create(event, None)
        assert result["statusCode"] == 201
        call_kwargs = repo.create_agent.call_args[1]
        assert call_kwargs["configuration"]["system_prompt"] == "Hello"
        assert call_kwargs["configuration"]["tools"] == ["t1"]


# ---------------------------------------------------------------------------
# Tests: Get Agent
# ---------------------------------------------------------------------------


class TestGetAgent:
    """Test single-agent retrieval handler."""

    @patch.object(mod, "_init")
    def test_get_agent_success(self, mock_init: MagicMock):
        repo = MagicMock()
        mock_init.return_value = (MagicMock(), repo, MagicMock())

        repo.get_agent.return_value = {
            "agentId": "a1",
            "userId": "user-1",
            "name": "TestAgent",
        }

        event = _api_event("GET", path_params={"agentId": "a1"})
        result = mod._handle_get(event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["agentId"] == "a1"

    @patch.object(mod, "_init")
    def test_get_agent_not_found(self, mock_init: MagicMock):
        repo = MagicMock()
        mock_init.return_value = (MagicMock(), repo, MagicMock())
        repo.get_agent.side_effect = ItemNotFoundError("not found")

        event = _api_event("GET", path_params={"agentId": "missing"})
        result = mod._handle_get(event, None)
        assert result["statusCode"] == 404


# ---------------------------------------------------------------------------
# Tests: List Agents
# ---------------------------------------------------------------------------


class TestListAgents:
    """Test agent listing handler."""

    @patch.object(mod, "_init")
    def test_list_agents_success(self, mock_init: MagicMock):
        repo = MagicMock()
        mock_init.return_value = (MagicMock(), repo, MagicMock())

        repo.list_agents_by_user.return_value = (
            [{"agentId": "a1", "name": "Agent1"}],
            None,
        )

        event = _api_event("GET")
        result = mod._handle_list(event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert len(body["agents"]) == 1
        assert "nextToken" not in body

    @patch.object(mod, "_init")
    def test_list_agents_with_pagination(self, mock_init: MagicMock):
        repo = MagicMock()
        mock_init.return_value = (MagicMock(), repo, MagicMock())

        last_key = {"PK": "AGENT#a1", "SK": "METADATA"}
        repo.list_agents_by_user.return_value = (
            [{"agentId": "a1"}],
            last_key,
        )

        event = _api_event("GET")
        result = mod._handle_list(event, None)

        body = json.loads(result["body"])
        assert "nextToken" in body


# ---------------------------------------------------------------------------
# Tests: Update Agent
# ---------------------------------------------------------------------------


class TestUpdateAgent:
    """Test agent update handler."""

    @patch.object(mod, "_init")
    def test_update_agent_success(self, mock_init: MagicMock):
        repo = MagicMock()
        mock_init.return_value = (MagicMock(), repo, MagicMock())

        repo.update_agent.return_value = {
            "agentId": "a1",
            "name": "Updated",
            "status": "idle",
        }

        event = _api_event("PUT", path_params={"agentId": "a1"}, body={"name": "Updated"})
        result = mod._handle_update(event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["name"] == "Updated"

    @patch.object(mod, "_init")
    def test_update_agent_not_found(self, mock_init: MagicMock):
        repo = MagicMock()
        mock_init.return_value = (MagicMock(), repo, MagicMock())
        repo.update_agent.side_effect = ItemNotFoundError("not found")

        event = _api_event("PUT", path_params={"agentId": "a1"}, body={"name": "X"})
        result = mod._handle_update(event, None)
        assert result["statusCode"] == 404

    @patch.object(mod, "_init")
    def test_update_agent_invalid_status(self, mock_init: MagicMock):
        mock_init.return_value = (MagicMock(), MagicMock(), MagicMock())
        event = _api_event("PUT", path_params={"agentId": "a1"}, body={"status": "bogus"})
        result = mod._handle_update(event, None)
        assert result["statusCode"] == 400

    @patch.object(mod, "_init")
    def test_update_agent_empty_body(self, mock_init: MagicMock):
        mock_init.return_value = (MagicMock(), MagicMock(), MagicMock())
        event = _api_event("PUT", path_params={"agentId": "a1"}, body={})
        result = mod._handle_update(event, None)
        assert result["statusCode"] == 400


# ---------------------------------------------------------------------------
# Tests: Delete Agent
# ---------------------------------------------------------------------------


class TestDeleteAgent:
    """Test agent deletion handler."""

    @patch.object(mod, "_init")
    def test_delete_agent_success(self, mock_init: MagicMock):
        repo = MagicMock()
        publisher = MagicMock()
        mock_init.return_value = (MagicMock(), repo, publisher)

        event = _api_event("DELETE", path_params={"agentId": "a1"})
        result = mod._handle_delete(event, None)

        assert result["statusCode"] == 204
        repo.delete_agent.assert_called_once_with("a1", user_id="user-1")
        publisher.publish_agent_deleted.assert_called_once_with(
            agent_id="a1", user_id="user-1"
        )

    @patch.object(mod, "_init")
    def test_delete_agent_not_found(self, mock_init: MagicMock):
        repo = MagicMock()
        mock_init.return_value = (MagicMock(), repo, MagicMock())
        repo.delete_agent.side_effect = ItemNotFoundError("not found")

        event = _api_event("DELETE", path_params={"agentId": "missing"})
        result = mod._handle_delete(event, None)
        assert result["statusCode"] == 404


# ---------------------------------------------------------------------------
# Tests: Pydantic Validation
# ---------------------------------------------------------------------------


class TestValidationModels:
    """Test Pydantic request validation models."""

    def test_create_agent_request_valid(self):
        req = mod.CreateAgentRequest(name="MyAgent")
        assert req.name == "MyAgent"
        assert req.configuration == {}

    def test_create_agent_request_empty_name(self):
        with pytest.raises(Exception):
            mod.CreateAgentRequest(name="")

    def test_update_agent_request_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid status"):
            mod.UpdateAgentRequest(status="nonexistent")

    def test_update_agent_request_valid_status(self):
        req = mod.UpdateAgentRequest(status="idle")
        assert req.status == "idle"


# ---------------------------------------------------------------------------
# Tests: Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test utility functions."""

    def test_sanitise_item_removes_keys(self):
        item = {"PK": "x", "SK": "y", "GSI1PK": "z", "GSI1SK": "w", "agentId": "a1"}
        result = mod._sanitise_item(item)
        assert result == {"agentId": "a1"}

    def test_parse_body_json_string(self):
        event = {"body": '{"name": "test"}'}
        result = mod._parse_body(event)
        assert result == {"name": "test"}

    def test_parse_body_none(self):
        event = {}
        result = mod._parse_body(event)
        assert result is None

    def test_parse_body_invalid_json(self):
        event = {"body": "not json"}
        result = mod._parse_body(event)
        assert result is None

    def test_response_format(self):
        result = mod._response(200, {"key": "value"})
        assert result["statusCode"] == 200
        assert result["headers"]["Content-Type"] == "application/json"
        assert json.loads(result["body"]) == {"key": "value"}

    def test_response_empty_body(self):
        result = mod._response(204, None)
        assert result["statusCode"] == 204
        assert result["body"] == ""
