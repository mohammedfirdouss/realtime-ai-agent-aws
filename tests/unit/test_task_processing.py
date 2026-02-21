"""Tests for runtime.handlers.task_processing module."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from runtime.handlers.task_processing import (
    _error_response,
    _handle_task_failure,
    _process_task,
    handler,
)


class TestHandler:
    """Tests for the task processing Lambda handler."""

    @patch("runtime.handlers.task_processing._init")
    @patch("runtime.handlers.task_processing._process_task")
    def test_handler_with_detail(
        self, mock_process: MagicMock, mock_init: MagicMock
    ) -> None:
        mock_init.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        mock_process.return_value = {"taskId": "t1", "status": "completed"}

        event = {
            "detail": {
                "taskId": "t1",
                "agentId": "a1",
                "description": "Test task",
            }
        }
        result = handler(event, None)
        assert result["taskId"] == "t1"

    @patch("runtime.handlers.task_processing._init")
    @patch("runtime.handlers.task_processing._process_task")
    def test_handler_direct_invocation(
        self, mock_process: MagicMock, mock_init: MagicMock
    ) -> None:
        mock_init.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        mock_process.return_value = {"taskId": "t2", "status": "completed"}

        event = {"taskId": "t2", "agentId": "a2"}
        result = handler(event, None)
        assert result["taskId"] == "t2"

    def test_handler_missing_fields(self) -> None:
        event = {"detail": {"taskId": ""}}
        result = handler(event, None)
        assert result["status"] == "error"
        assert "Missing required" in result["message"]

    @patch("runtime.handlers.task_processing._init")
    @patch("runtime.handlers.task_processing._process_task")
    def test_handler_catches_unhandled_error(
        self, mock_process: MagicMock, mock_init: MagicMock
    ) -> None:
        mock_init.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        mock_process.side_effect = RuntimeError("Unexpected")

        event = {"taskId": "t3", "agentId": "a3"}
        result = handler(event, None)
        assert result["status"] == "error"


class TestProcessTask:
    """Tests for _process_task function."""

    def _setup_mocks(self) -> dict[str, MagicMock]:
        config = MagicMock()
        config.aws_region = "us-east-1"

        agent_repo = MagicMock()
        agent_repo.get_agent.return_value = {
            "agentId": "a1",
            "configuration": {},
        }

        task_repo = MagicMock()
        task_repo.get_task.return_value = {
            "taskId": "t1",
            "agentId": "a1",
            "description": "Test task",
            "status": "pending",
        }
        task_repo.update_task_status.return_value = {}
        task_repo.update_task_plan.return_value = {}
        task_repo.update_current_step.return_value = {}
        task_repo.update_task_result.return_value = {}

        context_repo = MagicMock()
        context_repo.get_latest_context.return_value = {
            "conversationHistory": [],
            "agentMemory": {},
        }

        publisher = MagicMock()
        publisher.publish_task_progress.return_value = "event-id"
        publisher.publish_task_completed.return_value = "event-id"

        return {
            "config": config,
            "agent_repo": agent_repo,
            "task_repo": task_repo,
            "context_repo": context_repo,
            "publisher": publisher,
        }

    @patch("runtime.handlers.task_processing.AgentCapabilities")
    @patch("runtime.handlers.task_processing.create_agent_from_db_config")
    @patch("runtime.handlers.task_processing.ToolRegistry")
    def test_process_task_success(
        self,
        mock_registry_cls: MagicMock,
        mock_create_agent: MagicMock,
        mock_cap_cls: MagicMock,
    ) -> None:
        mocks = self._setup_mocks()
        mock_registry = MagicMock()
        mock_registry.get_strands_tools.return_value = []
        mock_registry_cls.return_value = mock_registry

        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_cap = MagicMock()
        mock_cap.plan_task.return_value = MagicMock(
            steps=[{"description": "Step 1", "type": "reasoning"}],
            to_dict=lambda: {"steps": [{"description": "Step 1", "type": "reasoning"}]},
        )
        mock_cap.execute_step.return_value = MagicMock(
            step_index=0,
            step_type="reasoning",
            status="completed",
            output="Done",
            error=None,
            tool_name=None,
            tool_input={},
            started_at="2026-01-01T00:00:00",
            completed_at="2026-01-01T00:00:01",
        )
        mock_cap.manage_memory.return_value = ([], {})
        mock_cap_cls.return_value = mock_cap

        result = _process_task(
            task_id="t1",
            agent_id="a1",
            **mocks,
        )

        assert result["status"] == "completed"
        assert result["taskId"] == "t1"
        assert len(result["steps"]) == 1
        mocks["publisher"].publish_task_completed.assert_called_once()

    @patch("runtime.handlers.task_processing.AgentCapabilities")
    @patch("runtime.handlers.task_processing.create_agent_from_db_config")
    @patch("runtime.handlers.task_processing.ToolRegistry")
    def test_process_task_step_failure(
        self,
        mock_registry_cls: MagicMock,
        mock_create_agent: MagicMock,
        mock_cap_cls: MagicMock,
    ) -> None:
        mocks = self._setup_mocks()
        mock_registry_cls.return_value = MagicMock(get_strands_tools=MagicMock(return_value=[]))
        mock_create_agent.return_value = MagicMock()

        mock_cap = MagicMock()
        mock_cap.plan_task.return_value = MagicMock(
            steps=[{"description": "Step 1", "type": "reasoning"}],
            to_dict=lambda: {"steps": []},
        )
        mock_cap.execute_step.return_value = MagicMock(
            step_index=0,
            step_type="reasoning",
            status="failed",
            output="",
            error="Step failed",
            tool_name=None,
            tool_input={},
            started_at="2026-01-01T00:00:00",
            completed_at="2026-01-01T00:00:01",
        )
        mock_cap.manage_memory.return_value = ([], {})
        mock_cap_cls.return_value = mock_cap

        result = _process_task(task_id="t1", agent_id="a1", **mocks)

        assert result["status"] == "failed"

    def test_process_task_agent_not_found(self) -> None:
        from runtime.repositories.base_repository import ItemNotFoundError

        mocks = self._setup_mocks()
        mocks["agent_repo"].get_agent.side_effect = ItemNotFoundError("Not found")

        result = _process_task(task_id="t1", agent_id="a1", **mocks)
        assert result["status"] == "error"

    def test_process_task_task_not_found(self) -> None:
        from runtime.repositories.base_repository import ItemNotFoundError

        mocks = self._setup_mocks()
        mocks["task_repo"].get_task.side_effect = ItemNotFoundError("Not found")

        result = _process_task(task_id="t1", agent_id="a1", **mocks)
        assert result["status"] == "error"


class TestHandleTaskFailure:
    """Tests for _handle_task_failure function."""

    def test_publishes_failure_events(self) -> None:
        task_repo = MagicMock()
        publisher = MagicMock()

        _handle_task_failure(
            task_id="t1",
            agent_id="a1",
            error="Something broke",
            task_repo=task_repo,
            publisher=publisher,
        )

        task_repo.update_task_status.assert_called_once_with("a1", "t1", "failed")
        task_repo.update_task_result.assert_called_once()
        publisher.publish_task_completed.assert_called_once()
        publisher.publish_error_occurred.assert_called_once()

    def test_handles_exception_gracefully(self) -> None:
        task_repo = MagicMock()
        task_repo.update_task_status.side_effect = RuntimeError("DB error")
        publisher = MagicMock()

        # Should not raise
        _handle_task_failure(
            task_id="t1",
            agent_id="a1",
            error="Error",
            task_repo=task_repo,
            publisher=publisher,
        )


class TestErrorResponse:
    """Tests for _error_response helper."""

    def test_format(self) -> None:
        result = _error_response("Bad thing happened")
        assert result["status"] == "error"
        assert result["message"] == "Bad thing happened"
