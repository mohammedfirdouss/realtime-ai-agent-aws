"""Agent Management Lambda handler.

Provides CRUD operations for AI agents via API Gateway proxy integration.
Routes requests based on HTTP method and path parameters.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from runtime.auth.middleware import require_permission
from runtime.repositories.agent_repository import AgentRepository
from runtime.repositories.base_repository import ItemNotFoundError
from runtime.shared.config import RuntimeConfig, load_runtime_config
from runtime.shared.constants import (
    MAX_SYSTEM_PROMPT_LENGTH,
    MAX_TOOLS_PER_AGENT,
    PERM_AGENT_CREATE,
    PERM_AGENT_DELETE,
    PERM_AGENT_READ,
    PERM_AGENT_UPDATE,
    VALID_AGENT_STATUSES,
)
from runtime.shared.event_publisher import EventPublisher

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Pydantic validation models
class CreateAgentRequest(BaseModel):
    """Validation model for agent creation requests."""

    name: str = Field(..., min_length=1, max_length=256)
    configuration: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str | None = Field(None, max_length=MAX_SYSTEM_PROMPT_LENGTH)
    tools: list[str] = Field(default_factory=list, max_length=MAX_TOOLS_PER_AGENT)
class UpdateAgentRequest(BaseModel):
    """Validation model for agent update requests."""

    name: str | None = Field(None, min_length=1, max_length=256)
    configuration: dict[str, Any] | None = None
    status: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.status is not None and self.status not in VALID_AGENT_STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}'. Must be one of: {sorted(VALID_AGENT_STATUSES)}"
            )
# Cold-start initialisation

_config: RuntimeConfig | None = None
_repo: AgentRepository | None = None
_publisher: EventPublisher | None = None
def _init() -> tuple[RuntimeConfig, AgentRepository, EventPublisher]:
    """Lazy-initialise shared resources on first invocation."""
    global _config, _repo, _publisher  # noqa: PLW0603
    if _config is None:
        _config = load_runtime_config()
        _repo = AgentRepository(
            _config.agents_table,
            region=_config.aws_region,
            endpoint_url=_config.dynamodb_endpoint,
        )
        _publisher = EventPublisher(_config)
    assert _repo is not None
    assert _publisher is not None
    return _config, _repo, _publisher
# Lambda entry point
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Route requests to the appropriate CRUD handler."""
    http_method = event.get("httpMethod", "").upper()
    path_params = event.get("pathParameters") or {}
    agent_id = path_params.get("agentId")

    routes: dict[tuple[str, bool], Any] = {
        ("POST", False): _handle_create,
        ("GET", False): _handle_list,
        ("GET", True): _handle_get,
        ("PUT", True): _handle_update,
        ("DELETE", True): _handle_delete,
    }

    route_handler = routes.get((http_method, agent_id is not None))
    if route_handler is None:
        return _response(405, {"message": f"Method {http_method} not allowed"})

    try:
        return route_handler(event, context)
    except Exception:
        logger.exception("Unhandled error in agent management handler")
        return _response(500, {"message": "Internal server error"})
# CRUD handlers
@require_permission(PERM_AGENT_CREATE)
def _handle_create(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Create a new agent."""
    _, repo, publisher = _init()
    auth = _get_auth_context(event)
    user_id = auth["user_id"]

    body = _parse_body(event)
    if body is None:
        return _response(400, {"message": "Request body is required"})

    try:
        request = CreateAgentRequest(**body)
    except ValidationError as exc:
        return _response(400, {"message": "Validation error", "errors": exc.errors()})

    configuration = request.configuration
    if request.system_prompt is not None:
        configuration["system_prompt"] = request.system_prompt
    if request.tools:
        configuration["tools"] = request.tools

    agent = repo.create_agent(
        user_id=user_id,
        name=request.name,
        configuration=configuration,
    )

    # Publish lifecycle event
    publisher.publish_agent_created(
        agent_id=agent["agentId"],
        user_id=user_id,
        agent_name=request.name,
    )

    return _response(201, _sanitise_item(agent))
@require_permission(PERM_AGENT_READ)
def _handle_list(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """List agents for the authenticated user."""
    _, repo, _ = _init()
    auth = _get_auth_context(event)
    user_id = auth["user_id"]

    qs = event.get("queryStringParameters") or {}
    limit = min(int(qs.get("limit", "25")), 100)
    exclusive_start_key = qs.get("nextToken")

    start_key = None
    if exclusive_start_key:
        try:
            start_key = json.loads(exclusive_start_key)
        except (json.JSONDecodeError, TypeError):
            return _response(400, {"message": "Invalid nextToken"})

    agents, last_key = repo.list_agents_by_user(
        user_id,
        limit=limit,
        exclusive_start_key=start_key,
    )

    result: dict[str, Any] = {"agents": [_sanitise_item(a) for a in agents]}
    if last_key:
        result["nextToken"] = json.dumps(last_key)

    return _response(200, result)
@require_permission(PERM_AGENT_READ)
def _handle_get(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Get a single agent by ID."""
    _, repo, _ = _init()
    auth = _get_auth_context(event)
    agent_id = event["pathParameters"]["agentId"]

    try:
        agent = repo.get_agent(agent_id, user_id=auth["user_id"])
    except ItemNotFoundError:
        return _response(404, {"message": "Agent not found"})

    return _response(200, _sanitise_item(agent))
@require_permission(PERM_AGENT_UPDATE)
def _handle_update(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Update an existing agent."""
    _, repo, _ = _init()
    auth = _get_auth_context(event)
    agent_id = event["pathParameters"]["agentId"]

    body = _parse_body(event)
    if body is None:
        return _response(400, {"message": "Request body is required"})

    try:
        request = UpdateAgentRequest(**body)
    except (ValidationError, ValueError) as exc:
        errors = exc.errors() if isinstance(exc, ValidationError) else [{"msg": str(exc)}]
        return _response(400, {"message": "Validation error", "errors": errors})

    updates: dict[str, Any] = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.configuration is not None:
        updates["configuration"] = request.configuration
    if request.status is not None:
        updates["status"] = request.status

    if not updates:
        return _response(400, {"message": "No valid fields to update"})

    try:
        agent = repo.update_agent(
            agent_id,
            updates=updates,
            user_id=auth["user_id"],
        )
    except ItemNotFoundError:
        return _response(404, {"message": "Agent not found"})

    return _response(200, _sanitise_item(agent))
@require_permission(PERM_AGENT_DELETE)
def _handle_delete(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Delete an agent."""
    _, repo, publisher = _init()
    auth = _get_auth_context(event)
    agent_id = event["pathParameters"]["agentId"]

    try:
        repo.delete_agent(agent_id, user_id=auth["user_id"])
    except ItemNotFoundError:
        return _response(404, {"message": "Agent not found"})

    # Publish lifecycle event
    publisher.publish_agent_deleted(
        agent_id=agent_id,
        user_id=auth["user_id"],
    )

    return _response(204, None)
# Helpers
def _get_auth_context(event: dict[str, Any]) -> dict[str, str]:
    """Extract authorizer context from the API Gateway event."""
    rc = event.get("requestContext") or {}
    authorizer = rc.get("authorizer") or {}
    return {
        "user_id": str(authorizer.get("user_id", "")),
        "role": str(authorizer.get("role", "")),
    }
def _parse_body(event: dict[str, Any]) -> dict[str, Any] | None:
    """Parse the JSON body from an API Gateway event."""
    body = event.get("body")
    if body is None:
        return None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return None
    return body if isinstance(body, dict) else None
def _sanitise_item(item: dict[str, Any]) -> dict[str, Any]:
    """Remove DynamoDB key attributes from the response."""
    internal_keys = {"PK", "SK", "GSI1PK", "GSI1SK"}
    return {k: v for k, v in item.items() if k not in internal_keys}
def _response(status_code: int, body: Any) -> dict[str, Any]:
    """Build an API Gateway proxy integration response."""
    result: dict[str, Any] = {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
    }
    if body is not None:
        result["body"] = json.dumps(body, default=str)
    else:
        result["body"] = ""
    return result
