"""Shared configuration and environment settings for CDK infrastructure."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EnvironmentConfig:
    """Immutable configuration for a deployment environment."""

    stage: str
    aws_account_id: str
    aws_region: str

    # Naming
    project_name: str = "realtime-agentic-api"

    # VPC
    vpc_cidr: str = "10.0.0.0/16"
    max_azs: int = 2
    nat_gateways: int = 1

    # Lambda defaults
    lambda_memory_mb: int = 256
    lambda_timeout_seconds: int = 30
    lambda_runtime_python: str = "python3.11"
    task_lambda_memory_mb: int = 1024
    task_lambda_timeout_seconds: int = 300

    # DynamoDB
    dynamodb_billing_mode: str = "PAY_PER_REQUEST"

    # Cache
    cache_node_type: str = "cache.t3.micro"
    cache_num_nodes: int = 1

    # Secrets
    secrets_prefix: str = "realtime-agentic-api"

    # EventBridge
    event_bus_name: str = "realtime-agentic-api-events"

    # Tags
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def resource_prefix(self) -> str:
        return f"{self.project_name}-{self.stage}"

    def resource_name(self, name: str) -> str:
        return f"{self.resource_prefix}-{name}"
# Pre-defined environment configurations
# NOTE: aws_account_id values are placeholders; set them to your AWS account IDs before deploy.
_ENV_CONFIGS: dict[str, dict[str, object]] = {
    "dev": {
        "stage": "dev",
        "aws_account_id": "000000000000",
        "aws_region": "us-east-1",
        "nat_gateways": 0,
        "tags": {"Environment": "dev", "Project": "realtime-agentic-api"},
    },
    "staging": {
        "stage": "staging",
        "aws_account_id": "000000000000",
        "aws_region": "us-east-1",
        "nat_gateways": 1,
        "tags": {"Environment": "staging", "Project": "realtime-agentic-api"},
    },
    "prod": {
        "stage": "prod",
        "aws_account_id": "000000000000",
        "aws_region": "us-east-1",
        "max_azs": 3,
        "nat_gateways": 2,
        "lambda_memory_mb": 512,
        "cache_node_type": "cache.t3.small",
        "tags": {"Environment": "prod", "Project": "realtime-agentic-api"},
    },
}
def get_environment_config(env_name: str) -> EnvironmentConfig:
    """Get configuration for the given environment name.

    Args:
        env_name: One of 'dev', 'staging', 'prod' or a custom name.

    Returns:
        EnvironmentConfig for the requested environment.

    Raises:
        ValueError: If env_name is not recognized.
    """
    if env_name not in _ENV_CONFIGS:
        raise ValueError(
            f"Unknown environment '{env_name}'. Choose from: {list(_ENV_CONFIGS.keys())}"
        )
    return EnvironmentConfig(**_ENV_CONFIGS[env_name])  # type: ignore[arg-type]
