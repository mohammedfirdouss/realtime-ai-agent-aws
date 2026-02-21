"""Tests for runtime.agent.tool_registry module."""

from __future__ import annotations

from typing import Any

import pytest

from runtime.agent.tool_registry import (
    ToolDefinition,
    ToolError,
    ToolInvocation,
    ToolNotFoundError,
    ToolRegistry,
    ToolValidationError,
)


def _echo_tool(**kwargs: Any) -> str:
    return f"echo: {kwargs}"


def _failing_tool(**kwargs: Any) -> str:
    raise RuntimeError("Tool broke")


class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    def test_defaults(self) -> None:
        td = ToolDefinition(name="test", description="desc", handler=_echo_tool)
        assert td.name == "test"
        assert td.parameters == {}
        assert td.required_params == frozenset()


class TestToolInvocation:
    """Tests for ToolInvocation dataclass."""

    def test_to_dict(self) -> None:
        inv = ToolInvocation(
            tool_name="test",
            parameters={"key": "val"},
            status="success",
            result="ok",
            duration_ms=42.5,
            timestamp="2026-01-01T00:00:00",
        )
        d = inv.to_dict()
        assert d["toolName"] == "test"
        assert d["status"] == "success"
        assert d["durationMs"] == 42.5


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_register_and_list(self) -> None:
        reg = ToolRegistry()
        reg.register("tool_a", _echo_tool, description="A")
        reg.register("tool_b", _echo_tool, description="B")

        assert reg.tool_names == ["tool_a", "tool_b"]

    def test_register_empty_name_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolValidationError, match="non-empty"):
            reg.register("", _echo_tool)

    def test_get_tool(self) -> None:
        reg = ToolRegistry()
        reg.register("my_tool", _echo_tool, description="My tool")

        tool = reg.get_tool("my_tool")
        assert tool.name == "my_tool"
        assert tool.description == "My tool"

    def test_get_tool_not_found(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError, match="not found"):
            reg.get_tool("missing")

    def test_unregister(self) -> None:
        reg = ToolRegistry()
        reg.register("tool_x", _echo_tool)
        reg.unregister("tool_x")
        assert "tool_x" not in reg.tool_names

    def test_unregister_missing_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            reg.unregister("missing")

    def test_validate_parameters_passes(self) -> None:
        reg = ToolRegistry()
        reg.register(
            "tool",
            _echo_tool,
            required_params=frozenset({"a", "b"}),
        )
        reg.validate_parameters("tool", {"a": 1, "b": 2, "c": 3})

    def test_validate_parameters_missing(self) -> None:
        reg = ToolRegistry()
        reg.register(
            "tool",
            _echo_tool,
            required_params=frozenset({"a", "b"}),
        )
        with pytest.raises(ToolValidationError, match="missing required"):
            reg.validate_parameters("tool", {"a": 1})

    def test_execute_success(self) -> None:
        reg = ToolRegistry()
        reg.register("echo", _echo_tool)

        result = reg.execute("echo", {"msg": "hello"})
        assert "hello" in str(result)
        assert len(reg.invocation_log) == 1
        assert reg.invocation_log[0].status == "success"

    def test_execute_failure(self) -> None:
        reg = ToolRegistry()
        reg.register("fail", _failing_tool)

        with pytest.raises(ToolError, match="execution failed"):
            reg.execute("fail", {})

        assert len(reg.invocation_log) == 1
        assert reg.invocation_log[0].status == "error"
        assert "Tool broke" in reg.invocation_log[0].error

    def test_execute_validates_params(self) -> None:
        reg = ToolRegistry()
        reg.register(
            "strict",
            _echo_tool,
            required_params=frozenset({"required_field"}),
        )
        with pytest.raises(ToolValidationError):
            reg.execute("strict", {})

    def test_get_tool_definitions_for_agent(self) -> None:
        reg = ToolRegistry()
        reg.register(
            "tool1",
            _echo_tool,
            description="First tool",
            parameters={"type": "object"},
        )
        defs = reg.get_tool_definitions_for_agent()
        assert len(defs) == 1
        assert defs[0]["name"] == "tool1"
        assert defs[0]["description"] == "First tool"

    def test_get_strands_tools(self) -> None:
        reg = ToolRegistry()
        reg.register("tool1", _echo_tool)
        reg.register("tool2", _failing_tool)

        tools = reg.get_strands_tools()
        assert len(tools) == 2
        assert _echo_tool in tools

    def test_clear_invocation_log(self) -> None:
        reg = ToolRegistry()
        reg.register("echo", _echo_tool)
        reg.execute("echo", {})
        assert len(reg.invocation_log) == 1

        reg.clear_invocation_log()
        assert len(reg.invocation_log) == 0
