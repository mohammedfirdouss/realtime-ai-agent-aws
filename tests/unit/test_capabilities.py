"""Tests for runtime.agent.capabilities module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from runtime.agent.capabilities import (
    CONTEXT_SUMMARY_THRESHOLD,
    AgentCapabilities,
    StepResult,
    TaskPlan,
)
from runtime.shared.constants import (
    STEP_STATUS_COMPLETED,
    STEP_STATUS_FAILED,
    STEP_TYPE_REASONING,
    STEP_TYPE_RESPONSE,
    STEP_TYPE_TOOL_CALL,
)


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_default_values(self) -> None:
        result = StepResult(step_index=0, step_type="reasoning", status="running")
        assert result.output == ""
        assert result.error is None
        assert result.tool_name is None
        assert result.tool_input == {}


class TestTaskPlan:
    """Tests for TaskPlan dataclass."""

    def test_to_dict(self) -> None:
        plan = TaskPlan(
            task_id="t1",
            description="Test task",
            steps=[{"description": "step 1", "type": "reasoning"}],
            created_at="2026-01-01T00:00:00",
        )
        d = plan.to_dict()
        assert d["taskId"] == "t1"
        assert d["description"] == "Test task"
        assert len(d["steps"]) == 1
        assert d["createdAt"] == "2026-01-01T00:00:00"


class TestAgentCapabilities:
    """Tests for AgentCapabilities class."""

    def _make_capabilities(self, agent_response: str = "test response") -> tuple[AgentCapabilities, MagicMock]:
        mock_agent = MagicMock()
        mock_agent.return_value = agent_response
        return AgentCapabilities(mock_agent), mock_agent

    def test_agent_property(self) -> None:
        mock_agent = MagicMock()
        cap = AgentCapabilities(mock_agent)
        assert cap.agent is mock_agent

    def test_plan_task_parses_json(self) -> None:
        steps = [
            {"description": "Analyze", "type": "reasoning"},
            {"description": "Execute", "type": "tool_call", "tool_name": "search"},
        ]
        cap, _ = self._make_capabilities(json.dumps(steps))

        plan = cap.plan_task("task-1", "Do something")

        assert plan.task_id == "task-1"
        assert plan.description == "Do something"
        assert len(plan.steps) == 2
        assert plan.steps[0]["type"] == "reasoning"
        assert plan.steps[1]["tool_name"] == "search"

    def test_plan_task_handles_markdown_fences(self) -> None:
        steps = [{"description": "Step 1", "type": "reasoning"}]
        response = f"```json\n{json.dumps(steps)}\n```"
        cap, _ = self._make_capabilities(response)

        plan = cap.plan_task("task-2", "Do things")
        assert len(plan.steps) == 1

    def test_plan_task_fallback_on_invalid_json(self) -> None:
        cap, _ = self._make_capabilities("This is not JSON")

        plan = cap.plan_task("task-3", "Something")
        assert len(plan.steps) == 1
        assert plan.steps[0]["type"] == STEP_TYPE_REASONING

    def test_execute_step_reasoning(self) -> None:
        cap, mock_agent = self._make_capabilities("Thought process result")

        step = {"description": "Think about it", "type": STEP_TYPE_REASONING}
        result = cap.execute_step(step, 0)

        assert result.status == STEP_STATUS_COMPLETED
        assert result.step_type == STEP_TYPE_REASONING
        assert result.output == "Thought process result"
        assert result.error is None
        mock_agent.assert_called_once()

    def test_execute_step_tool_call(self) -> None:
        cap, _ = self._make_capabilities("Tool result")

        step = {
            "description": "Call tool",
            "type": STEP_TYPE_TOOL_CALL,
            "tool_name": "search",
            "tool_input": {"query": "test"},
        }
        result = cap.execute_step(step, 1)

        assert result.status == STEP_STATUS_COMPLETED
        assert result.tool_name == "search"
        assert result.tool_input == {"query": "test"}

    def test_execute_step_response(self) -> None:
        cap, _ = self._make_capabilities("Generated response")

        step = {"description": "Generate answer", "type": STEP_TYPE_RESPONSE}
        result = cap.execute_step(step, 2)

        assert result.status == STEP_STATUS_COMPLETED
        assert result.step_type == STEP_TYPE_RESPONSE

    def test_execute_step_handles_error(self) -> None:
        mock_agent = MagicMock(side_effect=RuntimeError("LLM failure"))
        cap = AgentCapabilities(mock_agent)

        step = {"description": "Fail step", "type": STEP_TYPE_REASONING}
        result = cap.execute_step(step, 0)

        assert result.status == STEP_STATUS_FAILED
        assert result.error == "LLM failure"

    def test_execute_step_with_context(self) -> None:
        cap, mock_agent = self._make_capabilities("Result with context")

        step = {"description": "Use context", "type": STEP_TYPE_REASONING}
        context = {"step_0": "previous output"}
        result = cap.execute_step(step, 1, context=context)

        assert result.status == STEP_STATUS_COMPLETED
        call_args = mock_agent.call_args[0][0]
        assert "previous output" in call_args

    def test_process_natural_language(self) -> None:
        cap, mock_agent = self._make_capabilities("Hello!")

        response = cap.process_natural_language("Hi there")

        assert response == "Hello!"
        mock_agent.assert_called_once()

    def test_process_natural_language_with_history(self) -> None:
        cap, mock_agent = self._make_capabilities("Response")

        history = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "First reply"},
        ]
        cap.process_natural_language("Follow up", conversation_history=history)

        prompt = mock_agent.call_args[0][0]
        assert "First message" in prompt
        assert "Follow up" in prompt

    def test_reason_multi_step_parses_json(self) -> None:
        traces = [
            {"step": 1, "thought": "Think", "decision": "Do X", "confidence": 0.9},
        ]
        cap, _ = self._make_capabilities(json.dumps(traces))

        result = cap.reason_multi_step("Solve problem")

        assert len(result) == 1
        assert result[0]["confidence"] == 0.9

    def test_reason_multi_step_fallback(self) -> None:
        cap, _ = self._make_capabilities("Not JSON reasoning")

        result = cap.reason_multi_step("Problem")

        assert len(result) == 1
        assert result[0]["step"] == 1
        assert "Not JSON reasoning" in result[0]["thought"]

    def test_manage_memory_below_threshold(self) -> None:
        cap, _ = self._make_capabilities()

        history = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        memory = {"key": "value"}

        trimmed, updated = cap.manage_memory(history, memory)

        assert trimmed == history
        assert updated == memory

    def test_manage_memory_above_threshold(self) -> None:
        cap, _ = self._make_capabilities("Summary of old messages")

        history = [
            {"role": "user", "content": f"msg {i}"}
            for i in range(CONTEXT_SUMMARY_THRESHOLD + 10)
        ]
        memory = {"existing": "data"}

        trimmed, updated = cap.manage_memory(history, memory)

        assert len(trimmed) == 20
        assert "conversation_summary" in updated
        assert updated["conversation_summary"] == "Summary of old messages"
        assert updated["existing"] == "data"


class TestExtractJson:
    """Tests for JSON extraction utility."""

    def test_plain_json(self) -> None:
        assert AgentCapabilities._extract_json('[{"a": 1}]') == '[{"a": 1}]'

    def test_json_with_fences(self) -> None:
        assert AgentCapabilities._extract_json('```json\n[1,2]\n```') == "[1,2]"

    def test_json_with_generic_fences(self) -> None:
        assert AgentCapabilities._extract_json('```\n{"x": 1}\n```') == '{"x": 1}'
