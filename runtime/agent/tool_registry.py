"""Tool registry for agent tool calling.

Provides a registry for tools that agents can invoke, with parameter
validation, execution error handling, and invocation logging.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from strands import tool

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Raised when a tool invocation fails."""


class ToolNotFoundError(ToolError):
    """Raised when a requested tool is not registered."""


class ToolValidationError(ToolError):
    """Raised when tool parameters fail validation."""


@dataclass(frozen=True)
class ToolDefinition:
    """Metadata and callable for a registered tool."""

    name: str
    description: str
    handler: Callable[..., Any]
    parameters: dict[str, Any] = field(default_factory=dict)
    required_params: frozenset[str] = field(default_factory=frozenset)


@dataclass
class ToolInvocation:
    """Record of a single tool invocation for logging."""

    tool_name: str
    parameters: dict[str, Any]
    status: str  # "success" or "error"
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "toolName": self.tool_name,
            "parameters": self.parameters,
            "status": self.status,
            "result": str(self.result) if self.result is not None else None,
            "error": self.error,
            "durationMs": self.duration_ms,
            "timestamp": self.timestamp,
        }


class ToolRegistry:
    """Registry for agent tools with validation and execution."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._invocation_log: list[ToolInvocation] = []

    @property
    def tool_names(self) -> list[str]:
        """Return sorted list of registered tool names."""
        return sorted(self._tools.keys())

    @property
    def invocation_log(self) -> list[ToolInvocation]:
        """Return the invocation log."""
        return list(self._invocation_log)

    def register(
        self,
        name: str,
        handler: Callable[..., Any],
        *,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        required_params: frozenset[str] | None = None,
    ) -> None:
        """Register a tool with the registry.

        Args:
            name: Unique tool name.
            handler: Callable that implements the tool.
            description: Human-readable description.
            parameters: JSON Schema for tool parameters.
            required_params: Set of required parameter names.
        """
        if not name or not name.strip():
            raise ToolValidationError("Tool name must be non-empty")

        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            handler=handler,
            parameters=parameters or {},
            required_params=required_params or frozenset(),
        )
        logger.info("Registered tool: %s", name)

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' not found")
        del self._tools[name]
        logger.info("Unregistered tool: %s", name)

    def get_tool(self, name: str) -> ToolDefinition:
        """Get a tool definition by name."""
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' not found")
        return self._tools[name]

    def validate_parameters(self, name: str, params: dict[str, Any]) -> None:
        """Validate parameters against the tool's requirements.

        Raises ToolValidationError if required parameters are missing.
        """
        tool_def = self.get_tool(name)
        missing = tool_def.required_params - set(params.keys())
        if missing:
            raise ToolValidationError(
                f"Tool '{name}' missing required parameters: {sorted(missing)}"
            )

    def execute(self, name: str, params: dict[str, Any]) -> Any:
        """Execute a tool with validated parameters.

        Validates parameters, invokes the handler, logs the invocation,
        and returns the result. Raises ToolError on failure.
        """
        self.validate_parameters(name, params)
        tool_def = self.get_tool(name)

        now = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        invocation = ToolInvocation(
            tool_name=name,
            parameters=params,
            status="running",
            timestamp=now,
        )

        try:
            result = tool_def.handler(**params)
            elapsed_ms = (time.monotonic() - start) * 1000
            invocation.status = "success"
            invocation.result = result
            invocation.duration_ms = elapsed_ms
            logger.info(
                "Tool '%s' executed successfully in %.1fms", name, elapsed_ms
            )
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            invocation.status = "error"
            invocation.error = str(exc)
            invocation.duration_ms = elapsed_ms
            logger.error("Tool '%s' failed after %.1fms: %s", name, elapsed_ms, exc)
            self._invocation_log.append(invocation)
            raise ToolError(f"Tool '{name}' execution failed: {exc}") from exc

        self._invocation_log.append(invocation)
        return result

    def get_tool_definitions_for_agent(self) -> list[dict[str, Any]]:
        """Return tool definitions formatted for Strands Agent registration."""
        definitions = []
        for tool_def in self._tools.values():
            definitions.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "parameters": tool_def.parameters,
            })
        return definitions

    def get_strands_tools(self) -> list[Callable[..., Any]]:
        """Return tool handler callables for Strands Agent tool registration."""
        return [t.handler for t in self._tools.values()]

    def clear_invocation_log(self) -> None:
        """Clear the invocation log."""
        self._invocation_log.clear()


def create_strands_tool(
    name: str,
    description: str,
    handler: Callable[..., Any],
) -> Callable[..., Any]:
    """Wrap a function as a Strands-compatible tool using the @tool decorator.

    This creates a decorated function that Strands Agent can discover and invoke.
    """
    @tool(name=name, description=description)
    def wrapper(**kwargs: Any) -> Any:
        return handler(**kwargs)

    return wrapper
