"""Runtime configuration loaded from environment variables.

Lambda functions read these values at cold-start to configure
connections to DynamoDB, EventBridge, Secrets Manager, etc.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime configuration sourced from Lambda environment variables."""

    stage: str
    aws_region: str

    # DynamoDB table names
    agents_table: str
    tasks_table: str
    context_table: str
    connections_table: str

    # EventBridge
    event_bus_name: str

    # Secrets Manager
    secrets_prefix: str

    # Cache (ElastiCache Redis)
    cache_endpoint: str | None = None
    cache_port: int = 6379

    # Auth
    api_keys_secret_name: str | None = None
    jwt_secret_name: str | None = None
    jwt_algorithm: str = "HS256"

    # Optional overrides (useful for local testing)
    dynamodb_endpoint: str | None = None
    eventbridge_endpoint: str | None = None


def load_runtime_config() -> RuntimeConfig:
    """Build RuntimeConfig from environment variables set by CDK."""
    cache_port = int(os.environ.get("CACHE_PORT", "6379"))

    return RuntimeConfig(
        stage=os.environ.get("STAGE", "dev"),
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
        agents_table=os.environ["AGENTS_TABLE"],
        tasks_table=os.environ["TASKS_TABLE"],
        context_table=os.environ["CONTEXT_TABLE"],
        connections_table=os.environ["CONNECTIONS_TABLE"],
        event_bus_name=os.environ["EVENT_BUS_NAME"],
        secrets_prefix=os.environ.get("SECRETS_PREFIX", "realtime-agentic-api"),
        cache_endpoint=os.environ.get("CACHE_ENDPOINT"),
        cache_port=cache_port,
        api_keys_secret_name=os.environ.get("API_KEYS_SECRET_NAME"),
        jwt_secret_name=os.environ.get("JWT_SECRET_NAME"),
        jwt_algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        dynamodb_endpoint=os.environ.get("DYNAMODB_ENDPOINT"),
        eventbridge_endpoint=os.environ.get("EVENTBRIDGE_ENDPOINT"),
    )
