#!/usr/bin/env python3
"""CDK application entry point for the Realtime Agentic API."""

import aws_cdk as cdk

from infra.config import get_environment_config
from infra.foundation_stack import FoundationStack

app = cdk.App()

env_name = app.node.try_get_context("env") or "dev"
config = get_environment_config(env_name)

env = cdk.Environment(
    account=config.aws_account_id,
    region=config.aws_region,
)

FoundationStack(
    app,
    f"RealtimeAgenticApi-Foundation-{config.stage}",
    config=config,
    env=env,
    description=f"Realtime Agentic API foundation infrastructure ({config.stage})",
)

app.synth()
