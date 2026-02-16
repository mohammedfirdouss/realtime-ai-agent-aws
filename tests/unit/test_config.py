"""Unit tests for the configuration module."""

import pytest

from infra.config import EnvironmentConfig, get_environment_config


class TestEnvironmentConfig:
    def test_resource_prefix(self) -> None:
        config = EnvironmentConfig(
            stage="dev", aws_account_id="123456789012", aws_region="us-east-1"
        )
        assert config.resource_prefix == "realtime-agentic-api-dev"

    def test_resource_name(self) -> None:
        config = EnvironmentConfig(
            stage="staging", aws_account_id="123456789012", aws_region="us-east-1"
        )
        assert config.resource_name("vpc") == "realtime-agentic-api-staging-vpc"

    def test_frozen(self) -> None:
        config = EnvironmentConfig(
            stage="dev", aws_account_id="123456789012", aws_region="us-east-1"
        )
        with pytest.raises(AttributeError):
            config.stage = "prod"  # type: ignore[misc]


class TestGetEnvironmentConfig:
    def test_dev(self) -> None:
        config = get_environment_config("dev")
        assert config.stage == "dev"
        assert config.nat_gateways == 0

    def test_staging(self) -> None:
        config = get_environment_config("staging")
        assert config.stage == "staging"
        assert config.nat_gateways == 1

    def test_prod(self) -> None:
        config = get_environment_config("prod")
        assert config.stage == "prod"
        assert config.nat_gateways == 2
        assert config.max_azs == 3

    def test_unknown_env_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown environment"):
            get_environment_config("unknown")
