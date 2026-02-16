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

    # Optional overrides (useful for local testing)
    dynamodb_endpoint: str | None = None
    eventbridge_endpoint: str | None = None


def load_runtime_config() -> RuntimeConfig:
    """Build RuntimeConfig from environment variables set by CDK."""
    cache_port_str = os.environ.get("CACHE_PORT", "6379")
    cache_port = int(cache_port_str) if cache_port_str else 6379

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
        dynamodb_endpoint=os.environ.get("DYNAMODB_ENDPOINT"),
        eventbridge_endpoint=os.environ.get("EVENTBRIDGE_ENDPOINT"),
    )
