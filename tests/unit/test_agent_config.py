"""Tests for runtime.agent.agent_config module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from runtime.agent.agent_config import (
    DEFAULT_MODEL_ID,
    DEFAULT_SYSTEM_PROMPT,
    AgentConfig,
    create_agent,
    create_agent_from_db_config,
    create_bedrock_model,
)
from runtime.shared.constants import LLM_PROVIDER_ANTHROPIC, LLM_PROVIDER_OPENAI


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_default_config(self) -> None:
        config = AgentConfig()
        assert config.model_id == DEFAULT_MODEL_ID
        assert config.system_prompt == DEFAULT_SYSTEM_PROMPT
        assert config.provider == LLM_PROVIDER_ANTHROPIC
        assert config.temperature == 0.7
        assert config.max_tokens == 4096
        assert config.tools == []

    def test_custom_config(self) -> None:
        config = AgentConfig(
            model_id="custom-model",
            system_prompt="Custom prompt",
            provider=LLM_PROVIDER_OPENAI,
            temperature=0.5,
            max_tokens=2048,
        )
        assert config.model_id == "custom-model"
        assert config.provider == LLM_PROVIDER_OPENAI

    def test_invalid_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            AgentConfig(provider="invalid")

    def test_invalid_max_tokens_raises(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be >= 1"):
            AgentConfig(max_tokens=0)


class TestCreateBedrockModel:
    """Tests for create_bedrock_model function."""

    @patch("runtime.agent.agent_config.BedrockModel")
    def test_creates_model_with_defaults(self, mock_bedrock: MagicMock) -> None:
        create_bedrock_model()
        mock_bedrock.assert_called_once_with(
            model_id=DEFAULT_MODEL_ID,
            max_tokens=4096,
        )

    @patch("runtime.agent.agent_config.BedrockModel")
    def test_creates_model_with_region(self, mock_bedrock: MagicMock) -> None:
        create_bedrock_model(region="us-west-2")
        mock_bedrock.assert_called_once_with(
            model_id=DEFAULT_MODEL_ID,
            max_tokens=4096,
            region_name="us-west-2",
        )

    @patch("runtime.agent.agent_config.BedrockModel")
    def test_creates_model_with_custom_params(self, mock_bedrock: MagicMock) -> None:
        create_bedrock_model(
            model_id="custom-model",
            temperature=0.3,
            max_tokens=1024,
        )
        mock_bedrock.assert_called_once_with(
            model_id="custom-model",
            max_tokens=1024,
        )


class TestCreateAgent:
    """Tests for create_agent function."""

    @patch("runtime.agent.agent_config.Agent")
    @patch("runtime.agent.agent_config.create_bedrock_model")
    def test_creates_agent_with_config(
        self, mock_model: MagicMock, mock_agent_cls: MagicMock
    ) -> None:
        mock_model_instance = MagicMock()
        mock_model.return_value = mock_model_instance
        config = AgentConfig()

        create_agent(config, region="us-east-1")

        mock_model.assert_called_once()
        mock_agent_cls.assert_called_once_with(
            model=mock_model_instance,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            tools=[],
        )

    @patch("runtime.agent.agent_config.Agent")
    @patch("runtime.agent.agent_config.create_bedrock_model")
    def test_creates_agent_with_tools(
        self, mock_model: MagicMock, mock_agent_cls: MagicMock
    ) -> None:
        mock_model.return_value = MagicMock()
        tool_fn = MagicMock()
        config = AgentConfig(tools=[tool_fn])

        create_agent(config)

        call_kwargs = mock_agent_cls.call_args[1]
        assert call_kwargs["tools"] == [tool_fn]


class TestCreateAgentFromDbConfig:
    """Tests for create_agent_from_db_config function."""

    @patch("runtime.agent.agent_config.create_agent")
    def test_creates_from_db_record(self, mock_create: MagicMock) -> None:
        mock_create.return_value = MagicMock()
        record = {
            "agentId": "agent-123",
            "configuration": {
                "model_id": "custom-model",
                "system_prompt": "Do stuff",
                "provider": LLM_PROVIDER_ANTHROPIC,
                "temperature": 0.5,
                "max_tokens": 2048,
            },
        }

        create_agent_from_db_config(record, region="us-east-1")

        call_args = mock_create.call_args
        config = call_args[0][0]
        assert config.model_id == "custom-model"
        assert config.system_prompt == "Do stuff"
        assert config.temperature == 0.5
        assert call_args[1]["region"] == "us-east-1"

    @patch("runtime.agent.agent_config.create_agent")
    def test_uses_defaults_for_missing_config(self, mock_create: MagicMock) -> None:
        mock_create.return_value = MagicMock()
        record = {"agentId": "agent-456", "configuration": {}}

        create_agent_from_db_config(record)

        config = mock_create.call_args[0][0]
        assert config.model_id == DEFAULT_MODEL_ID
        assert config.system_prompt == DEFAULT_SYSTEM_PROMPT

    @patch("runtime.agent.agent_config.create_agent")
    def test_passes_tool_functions(self, mock_create: MagicMock) -> None:
        mock_create.return_value = MagicMock()
        tool_fn = MagicMock()
        record = {"agentId": "agent-789", "configuration": {}}

        create_agent_from_db_config(record, tool_functions=[tool_fn])

        config = mock_create.call_args[0][0]
        assert config.tools == [tool_fn]
