"""Unit tests for runtime.shared.config."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from runtime.shared.config import load_runtime_config

_REQUIRED_ENV = {
    "AGENTS_TABLE": "agents",
    "TASKS_TABLE": "tasks",
    "CONTEXT_TABLE": "context",
    "CONNECTIONS_TABLE": "connections",
    "EVENT_BUS_NAME": "bus",
}
class TestLoadRuntimeConfig:
    def test_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=True):
            config = load_runtime_config()

        assert config.stage == "dev"
        assert config.aws_region == "us-east-1"
        assert config.secrets_prefix == "realtime-agentic-api"
        assert config.cache_port == 6379

    def test_optional_overrides(self) -> None:
        env = {
            **_REQUIRED_ENV,
            "STAGE": "staging",
            "AWS_REGION": "us-west-2",
            "SECRETS_PREFIX": "custom",
            "CACHE_PORT": "6380",
            "DYNAMODB_ENDPOINT": "http://localhost:8000",
            "EVENTBRIDGE_ENDPOINT": "http://localhost:4010",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_runtime_config()

        assert config.stage == "staging"
        assert config.aws_region == "us-west-2"
        assert config.secrets_prefix == "custom"
        assert config.cache_port == 6380
        assert config.dynamodb_endpoint == "http://localhost:8000"
        assert config.eventbridge_endpoint == "http://localhost:4010"

    def test_missing_required_env_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(KeyError):
                load_runtime_config()
