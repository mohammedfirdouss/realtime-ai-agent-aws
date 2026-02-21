"""Task Processing Lambda handler.

Processes tasks assigned to agents using the Strands Agent framework.
Handles task planning, step execution, context management, and
event publishing for task lifecycle.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from runtime.agent.agent_config import create_agent_from_db_config
from runtime.agent.capabilities import AgentCapabilities, StepResult
from runtime.agent.tool_registry import ToolRegistry
from runtime.repositories.agent_repository import AgentRepository
from runtime.repositories.base_repository import ItemNotFoundError
from runtime.repositories.context_repository import ContextRepository
from runtime.repositories.task_repository import TaskRepository
from runtime.shared.config import RuntimeConfig, load_runtime_config
from runtime.shared.constants import (
    AGENT_STATUS_IDLE,
    AGENT_STATUS_PROCESSING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
)
from runtime.shared.event_publisher import EventPublisher

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Cold-start initialisation

_config: RuntimeConfig | None = None
_agent_repo: AgentRepository | None = None
_task_repo: TaskRepository | None = None
_context_repo: ContextRepository | None = None
_publisher: EventPublisher | None = None


def _init() -> (
    tuple[RuntimeConfig, AgentRepository, TaskRepository, ContextRepository, EventPublisher]
):
    """Lazy-initialise shared resources on first invocation."""
    global _config, _agent_repo, _task_repo, _context_repo, _publisher  # noqa: PLW0603
    if _config is None:
        _config = load_runtime_config()
        _agent_repo = AgentRepository(
            _config.agents_table,
            region=_config.aws_region,
            endpoint_url=_config.dynamodb_endpoint,
        )
        _task_repo = TaskRepository(
            _config.tasks_table,
            region=_config.aws_region,
            endpoint_url=_config.dynamodb_endpoint,
        )
        _context_repo = ContextRepository(
            _config.context_table,
            region=_config.aws_region,
            endpoint_url=_config.dynamodb_endpoint,
        )
        _publisher = EventPublisher(_config)
    assert _agent_repo is not None
    assert _task_repo is not None
    assert _context_repo is not None
    assert _publisher is not None
    return _config, _agent_repo, _task_repo, _context_repo, _publisher


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Process a task event.

    Expected event format (from EventBridge or direct invocation):
        {
            "detail": {
                "taskId": "...",
                "agentId": "...",
                "description": "..."
            }
        }

    Or direct invocation:
        {
            "taskId": "...",
            "agentId": "...",
            "description": "..."
        }
    """
    detail = event.get("detail", event)
    task_id = detail.get("taskId", "")
    agent_id = detail.get("agentId", "")

    if not task_id or not agent_id:
        logger.error("Missing taskId or agentId in event: %s", json.dumps(event))
        return _error_response("Missing required fields: taskId, agentId")

    logger.info("Processing task %s for agent %s", task_id, agent_id)

    config, agent_repo, task_repo, context_repo, publisher = _init()

    try:
        result = _process_task(
            task_id=task_id,
            agent_id=agent_id,
            config=config,
            agent_repo=agent_repo,
            task_repo=task_repo,
            context_repo=context_repo,
            publisher=publisher,
        )
        return result
    except Exception:
        logger.exception("Unhandled error processing task %s", task_id)
        _handle_task_failure(
            task_id=task_id,
            agent_id=agent_id,
            error="Internal processing error",
            task_repo=task_repo,
            publisher=publisher,
        )
        return _error_response("Internal processing error")


def _process_task(
    *,
    task_id: str,
    agent_id: str,
    config: RuntimeConfig,
    agent_repo: AgentRepository,
    task_repo: TaskRepository,
    context_repo: ContextRepository,
    publisher: EventPublisher,
) -> dict[str, Any]:
    """Core task processing logic."""
    # Load agent configuration
    try:
        agent_record = agent_repo.get_agent(agent_id)
    except ItemNotFoundError:
        logger.error("Agent %s not found", agent_id)
        return _error_response(f"Agent {agent_id} not found")

    # Load task
    try:
        task_record = task_repo.get_task(agent_id, task_id)
    except ItemNotFoundError:
        logger.error("Task %s not found for agent %s", task_id, agent_id)
        return _error_response(f"Task {task_id} not found")

    # Update agent status to processing
    agent_repo.update_agent_status(agent_id, AGENT_STATUS_PROCESSING)

    # Update task status to running
    task_repo.update_task_status(agent_id, task_id, TASK_STATUS_RUNNING)

    # Load context
    context_data = context_repo.get_latest_context(agent_id)
    conversation_history = (
        context_data.get("conversationHistory", []) if context_data else []
    )

    # Create Strands Agent
    tool_registry = ToolRegistry()
    strands_agent = create_agent_from_db_config(
        agent_record,
        region=config.aws_region,
        tool_functions=tool_registry.get_strands_tools(),
    )
    capabilities = AgentCapabilities(strands_agent)

    # Plan the task
    description = task_record.get("description", "")
    plan = capabilities.plan_task(task_id, description)

    # Persist the plan
    task_repo.update_task_plan(agent_id, task_id, plan.to_dict())

    # Execute steps
    step_results: list[dict[str, Any]] = []
    step_context: dict[str, Any] = {}
    task_failed = False

    for idx, step in enumerate(plan.steps):
        # Publish progress
        progress_pct = int((idx / max(len(plan.steps), 1)) * 100)
        publisher.publish_task_progress(
            task_id=task_id,
            agent_id=agent_id,
            progress_pct=progress_pct,
            message=f"Executing step {idx + 1}/{len(plan.steps)}",
        )

        # Update current step
        task_repo.update_current_step(agent_id, task_id, idx)

        # Execute the step
        step_result = capabilities.execute_step(step, idx, context=step_context)

        result_dict = {
            "stepIndex": step_result.step_index,
            "stepType": step_result.step_type,
            "status": step_result.status,
            "output": step_result.output,
            "error": step_result.error,
            "toolName": step_result.tool_name,
            "startedAt": step_result.started_at,
            "completedAt": step_result.completed_at,
        }
        step_results.append(result_dict)

        # Accumulate context for subsequent steps
        step_context[f"step_{idx}"] = step_result.output

        if step_result.status == "failed":
            task_failed = True
            logger.error("Step %d failed: %s", idx, step_result.error)
            break

    # Handle memory management
    new_messages = [
        {"role": "user", "content": description},
        {"role": "assistant", "content": json.dumps(step_results, default=str)},
    ]
    conversation_history.extend(new_messages)

    trimmed_history, updated_memory = capabilities.manage_memory(
        conversation_history,
        context_data.get("agentMemory", {}) if context_data else {},
    )

    # Save context
    context_repo.put_context(
        agent_id=agent_id,
        conversation_history=trimmed_history,
        agent_memory=updated_memory,
        task_state={"taskId": task_id, "results": step_results},
    )

    # Finalize task
    if task_failed:
        final_status = TASK_STATUS_FAILED
    else:
        final_status = TASK_STATUS_COMPLETED

    task_repo.update_task_status(agent_id, task_id, final_status)
    task_repo.update_task_result(agent_id, task_id, {"steps": step_results})

    # Publish completion event
    publisher.publish_task_completed(
        task_id=task_id,
        agent_id=agent_id,
        status=final_status,
        result={"stepCount": len(step_results)},
    )

    # Reset agent status
    agent_repo.update_agent_status(agent_id, AGENT_STATUS_IDLE)

    # Publish progress 100%
    publisher.publish_task_progress(
        task_id=task_id,
        agent_id=agent_id,
        progress_pct=100,
        message="Task completed",
    )

    logger.info(
        "Task %s completed with status %s (%d steps)",
        task_id,
        final_status,
        len(step_results),
    )

    return {
        "taskId": task_id,
        "agentId": agent_id,
        "status": final_status,
        "steps": step_results,
    }


def _handle_task_failure(
    *,
    task_id: str,
    agent_id: str,
    error: str,
    task_repo: TaskRepository,
    publisher: EventPublisher,
) -> None:
    """Handle task failure by updating status and publishing events."""
    try:
        task_repo.update_task_status(agent_id, task_id, TASK_STATUS_FAILED)
        task_repo.update_task_result(agent_id, task_id, {"error": error})
        publisher.publish_task_completed(
            task_id=task_id,
            agent_id=agent_id,
            status=TASK_STATUS_FAILED,
            result={"error": error},
        )
        publisher.publish_error_occurred(
            error_code="TASK_PROCESSING_ERROR",
            error_message=error,
            agent_id=agent_id,
            task_id=task_id,
        )
    except Exception:
        logger.exception("Failed to handle task failure for %s", task_id)


def _error_response(message: str) -> dict[str, Any]:
    """Build an error response."""
    return {
        "status": "error",
        "message": message,
    }
