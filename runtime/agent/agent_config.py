"""Agent configuration and initialization using Strands Agent framework.

Creates and configures Strands Agent instances with LLM provider
integration, tool registration, and system prompts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from strands import Agent
from strands.models.bedrock import BedrockModel

from runtime.shared.constants import (
    LLM_PROVIDER_ANTHROPIC,
    VALID_LLM_PROVIDERS,
)

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are an autonomous AI agent. You can plan and execute multi-step tasks, "
    "use tools to interact with external systems, and maintain conversation context. "
    "Break complex tasks into clear steps and execute them systematically."
)

DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-20250514"


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for creating a Strands Agent instance."""

    model_id: str = DEFAULT_MODEL_ID
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    provider: str = LLM_PROVIDER_ANTHROPIC
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.provider not in VALID_LLM_PROVIDERS:
            raise ValueError(
                f"Unknown provider '{self.provider}'. Must be one of: {sorted(VALID_LLM_PROVIDERS)}"
            )
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")


def create_bedrock_model(
    model_id: str = DEFAULT_MODEL_ID,
    *,
    region: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> BedrockModel:
    """Create a Bedrock model for use with Strands Agent.

    Uses Amazon Bedrock as the default model provider, which supports
    both Anthropic Claude and other models via a unified API.
    """
    kwargs: dict[str, Any] = {
        "model_id": model_id,
        "max_tokens": max_tokens,
    }
    if region:
        kwargs["region_name"] = region

    return BedrockModel(**kwargs)


def create_agent(
    config: AgentConfig,
    *,
    region: str | None = None,
) -> Agent:
    """Create a configured Strands Agent instance.

    Args:
        config: Agent configuration with model, prompt, and tool settings.
        region: AWS region for Bedrock model access.

    Returns:
        A fully configured Strands Agent ready for task processing.
    """
    model = create_bedrock_model(
        model_id=config.model_id,
        region=region,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )

    agent = Agent(
        model=model,
        system_prompt=config.system_prompt,
        tools=config.tools if config.tools else [],
    )

    logger.info(
        "Created Strands Agent with model=%s, provider=%s, tools=%d",
        config.model_id,
        config.provider,
        len(config.tools),
    )

    return agent


def create_agent_from_db_config(
    agent_record: dict[str, Any],
    *,
    region: str | None = None,
    tool_functions: list[Any] | None = None,
) -> Agent:
    """Create a Strands Agent from a DynamoDB agent configuration record.

    Args:
        agent_record: Agent record from DynamoDB (as returned by AgentRepository).
        region: AWS region for Bedrock.
        tool_functions: List of tool functions to register with the agent.

    Returns:
        A configured Strands Agent instance.
    """
    db_config = agent_record.get("configuration", {})

    agent_config = AgentConfig(
        model_id=db_config.get("model_id", DEFAULT_MODEL_ID),
        system_prompt=db_config.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
        provider=db_config.get("provider", LLM_PROVIDER_ANTHROPIC),
        temperature=db_config.get("temperature", 0.7),
        max_tokens=db_config.get("max_tokens", 4096),
        tools=tool_functions or [],
    )

    return create_agent(agent_config, region=region)
