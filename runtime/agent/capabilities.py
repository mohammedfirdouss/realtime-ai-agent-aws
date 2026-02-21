"""Agent capabilities: task planning, reasoning, tool calling, memory management.

Wraps Strands Agent with higher-level capabilities for the platform,
integrating with DynamoDB repositories for state persistence.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from strands import Agent

from runtime.shared.constants import (
    STEP_STATUS_COMPLETED,
    STEP_STATUS_FAILED,
    STEP_STATUS_RUNNING,
    STEP_TYPE_REASONING,
    STEP_TYPE_RESPONSE,
    STEP_TYPE_TOOL_CALL,
)

logger = logging.getLogger(__name__)

MAX_REASONING_STEPS = 20
MAX_CONTEXT_MESSAGES = 100
CONTEXT_SUMMARY_THRESHOLD = 80


@dataclass
class StepResult:
    """Result of executing a single step in a task plan."""

    step_index: int
    step_type: str
    status: str
    output: str = ""
    error: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""


@dataclass
class TaskPlan:
    """Decomposed task plan with ordered steps."""

    task_id: str
    description: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "description": self.description,
            "steps": self.steps,
            "createdAt": self.created_at,
        }


class AgentCapabilities:
    """High-level agent capabilities wrapping Strands Agent.

    Provides task planning, multi-step reasoning, tool calling coordination,
    and memory management.
    """

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    @property
    def agent(self) -> Agent:
        return self._agent

    def plan_task(self, task_id: str, description: str) -> TaskPlan:
        """Decompose a task description into executable steps.

        Uses the LLM to analyze the task and create a structured plan.
        """
        planning_prompt = (
            f"Analyze the following task and create a step-by-step execution plan. "
            f"Return a JSON array of steps, where each step has: "
            f'"description" (what to do), "type" (one of: reasoning, tool_call, response, decision), '
            f'and optionally "tool_name" and "tool_input" for tool_call steps.\n\n'
            f"Task: {description}\n\n"
            f"Respond with ONLY a JSON array of steps, no other text."
        )

        result = self._agent(planning_prompt)
        response_text = str(result)

        steps = self._parse_plan_response(response_text)

        now = datetime.now(timezone.utc).isoformat()
        return TaskPlan(
            task_id=task_id,
            description=description,
            steps=steps,
            created_at=now,
        )

    def execute_step(
        self,
        step: dict[str, Any],
        step_index: int,
        *,
        context: dict[str, Any] | None = None,
    ) -> StepResult:
        """Execute a single step from a task plan.

        Args:
            step: Step definition from the task plan.
            step_index: Zero-based index of this step.
            context: Additional context from previous steps.

        Returns:
            StepResult with execution details.
        """
        now = datetime.now(timezone.utc).isoformat()
        step_type = step.get("type", STEP_TYPE_REASONING)
        description = step.get("description", "")

        result = StepResult(
            step_index=step_index,
            step_type=step_type,
            status=STEP_STATUS_RUNNING,
            started_at=now,
        )

        try:
            if step_type == STEP_TYPE_TOOL_CALL:
                result.tool_name = step.get("tool_name", "")
                result.tool_input = step.get("tool_input", {})
                output = self._execute_tool_step(step, context)
            elif step_type == STEP_TYPE_REASONING:
                output = self._execute_reasoning_step(description, context)
            elif step_type == STEP_TYPE_RESPONSE:
                output = self._execute_response_step(description, context)
            else:
                output = self._execute_reasoning_step(description, context)

            result.output = output
            result.status = STEP_STATUS_COMPLETED
        except Exception as exc:
            logger.exception("Step %d failed: %s", step_index, exc)
            result.error = str(exc)
            result.status = STEP_STATUS_FAILED

        result.completed_at = datetime.now(timezone.utc).isoformat()
        return result

    def process_natural_language(
        self,
        user_input: str,
        *,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Process natural language input and generate a response.

        Maintains conversation context by loading prior history.
        """
        if conversation_history:
            context_str = self._format_conversation_context(conversation_history)
            prompt = f"Previous conversation:\n{context_str}\n\nUser: {user_input}"
        else:
            prompt = user_input

        result = self._agent(prompt)
        return str(result)

    def reason_multi_step(
        self,
        problem: str,
        *,
        max_steps: int = MAX_REASONING_STEPS,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform multi-step reasoning on a problem.

        Returns a list of reasoning traces with decisions and rationale.
        """
        reasoning_prompt = (
            "Reason step-by-step about the following problem. "
            "For each step, provide your thought process and any decisions made. "
            "Return a JSON array where each element has: "
            '"step" (number), "thought" (reasoning), "decision" (what you decided), '
            '"confidence" (0.0-1.0).\n\n'
        )
        if context:
            reasoning_prompt += f"Context: {json.dumps(context)}\n\n"
        reasoning_prompt += f"Problem: {problem}\n\nRespond with ONLY a JSON array."

        result = self._agent(reasoning_prompt)
        response_text = str(result)

        try:
            traces = json.loads(self._extract_json(response_text))
            if isinstance(traces, list):
                return traces[:max_steps]
        except (json.JSONDecodeError, ValueError):
            logger.warning("Could not parse reasoning traces, returning raw")

        return [{"step": 1, "thought": response_text, "decision": "see thought", "confidence": 0.5}]

    def manage_memory(
        self,
        conversation_history: list[dict[str, Any]],
        agent_memory: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Manage agent memory by summarizing old context when needed.

        When conversation history exceeds the threshold, uses the LLM
        to create a summary and trims the history.

        Returns:
            Tuple of (trimmed_history, updated_memory).
        """
        if len(conversation_history) <= CONTEXT_SUMMARY_THRESHOLD:
            return conversation_history, agent_memory

        older_messages = conversation_history[:-20]
        recent_messages = conversation_history[-20:]

        summary_prompt = (
            "Summarize the following conversation history into key facts, "
            "decisions, and context that should be remembered. "
            "Return a concise summary.\n\n"
        )
        for msg in older_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            summary_prompt += f"{role}: {content}\n"

        result = self._agent(summary_prompt)
        summary = str(result)

        updated_memory = dict(agent_memory)
        updated_memory["conversation_summary"] = summary
        updated_memory["summary_timestamp"] = datetime.now(timezone.utc).isoformat()

        return recent_messages, updated_memory

    # Internal helpers

    def _execute_tool_step(
        self, step: dict[str, Any], context: dict[str, Any] | None
    ) -> str:
        """Execute a tool call step via the agent."""
        tool_name = step.get("tool_name", "")
        tool_input = step.get("tool_input", {})

        prompt = (
            f"Execute the following tool call and return the result:\n"
            f"Tool: {tool_name}\n"
            f"Input: {json.dumps(tool_input)}\n"
        )
        if context:
            prompt += f"Context from previous steps: {json.dumps(context)}\n"

        result = self._agent(prompt)
        return str(result)

    def _execute_reasoning_step(
        self, description: str, context: dict[str, Any] | None
    ) -> str:
        """Execute a reasoning step."""
        prompt = f"Think through and execute: {description}"
        if context:
            prompt += f"\n\nContext: {json.dumps(context)}"

        result = self._agent(prompt)
        return str(result)

    def _execute_response_step(
        self, description: str, context: dict[str, Any] | None
    ) -> str:
        """Execute a response generation step."""
        prompt = f"Generate a response for: {description}"
        if context:
            prompt += f"\n\nContext: {json.dumps(context)}"

        result = self._agent(prompt)
        return str(result)

    @staticmethod
    def _format_conversation_context(history: list[dict[str, Any]]) -> str:
        """Format conversation history into a readable string."""
        lines = []
        for msg in history[-MAX_CONTEXT_MESSAGES:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from text that may contain markdown fences."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    @staticmethod
    def _parse_plan_response(response_text: str) -> list[dict[str, Any]]:
        """Parse the LLM planning response into a list of steps."""
        cleaned = AgentCapabilities._extract_json(response_text)
        try:
            steps = json.loads(cleaned)
            if isinstance(steps, list):
                return steps
        except (json.JSONDecodeError, ValueError):
            logger.warning("Could not parse plan response as JSON")

        # Fallback: single reasoning step
        return [
            {
                "description": response_text,
                "type": STEP_TYPE_REASONING,
            }
        ]
