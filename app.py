#!/usr/bin/env python3
"""CDK application entry point for the Realtime Agentic API."""

import aws_cdk as cdk

from infra.agent_management_stack import AgentManagementStack
from infra.auth_stack import AuthStack
from infra.cache_stack import CacheStack
from infra.config import get_environment_config
from infra.database_stack import DatabaseStack
from infra.events_stack import EventsStack
from infra.foundation_stack import FoundationStack
from infra.task_processing_stack import TaskProcessingStack

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

cache = CacheStack(
    app,
    f"RealtimeAgenticApi-Cache-{config.stage}",
    config=config,
    vpc=foundation.vpc,
    cache_security_group=foundation.cache_sg,
    env=env,
    description=f"Realtime Agentic API cache resources ({config.stage})",
)
cache.add_dependency(foundation)

database = DatabaseStack(
    app,
    f"RealtimeAgenticApi-Database-{config.stage}",
    config=config,
    env=env,
    description=f"Realtime Agentic API DynamoDB tables ({config.stage})",
)
database.add_dependency(foundation)

events = EventsStack(
    app,
    f"RealtimeAgenticApi-Events-{config.stage}",
    config=config,
    env=env,
    description=f"Realtime Agentic API EventBridge resources ({config.stage})",
)
events.add_dependency(foundation)

auth = AuthStack(
    app,
    f"RealtimeAgenticApi-Auth-{config.stage}",
    config=config,
    env=env,
    description=f"Realtime Agentic API authentication resources ({config.stage})",
)
auth.add_dependency(foundation)

agent_management = AgentManagementStack(
    app,
    f"RealtimeAgenticApi-AgentManagement-{config.stage}",
    config=config,
    agents_table=database.agents_table,
    event_bus=events.event_bus,
    env=env,
    description=f"Realtime Agentic API agent management ({config.stage})",
)
agent_management.add_dependency(database)
agent_management.add_dependency(events)

task_processing = TaskProcessingStack(
    app,
    f"RealtimeAgenticApi-TaskProcessing-{config.stage}",
    config=config,
    agents_table=database.agents_table,
    tasks_table=database.tasks_table,
    context_table=database.context_table,
    event_bus=events.event_bus,
    env=env,
    description=f"Realtime Agentic API task processing ({config.stage})",
)
task_processing.add_dependency(database)
task_processing.add_dependency(events)

app.synth()
