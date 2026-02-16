#!/usr/bin/env python3
"""CDK application entry point for the Realtime Agentic API."""

import aws_cdk as cdk

from infra.cache_stack import CacheStack
from infra.config import get_environment_config
from infra.database_stack import DatabaseStack
from infra.foundation_stack import FoundationStack

app = cdk.App()

env_name = app.node.try_get_context("env") or "dev"
config = get_environment_config(env_name)

env = cdk.Environment(
    account=config.aws_account_id,
    region=config.aws_region,
)

foundation = FoundationStack(
    app,
    f"RealtimeAgenticApi-Foundation-{config.stage}",
    config=config,
    env=env,
    description=f"Realtime Agentic API foundation infrastructure ({config.stage})",
)

database = DatabaseStack(
    app,
    f"RealtimeAgenticApi-Database-{config.stage}",
    config=config,
    env=env,
    description=f"Realtime Agentic API DynamoDB tables ({config.stage})",
)
database.add_dependency(foundation)

cache = CacheStack(
    app,
    f"RealtimeAgenticApi-Cache-{config.stage}",
    config=config,
    vpc=foundation.vpc,
    cache_security_group=foundation.cache_sg,
    env=env,
    description=f"Realtime Agentic API ElastiCache Redis ({config.stage})",
)
cache.add_dependency(foundation)

app.synth()
