"""Tests for infra.task_processing_stack CDK stack."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import assertions

from infra.config import get_environment_config
from infra.database_stack import DatabaseStack
from infra.events_stack import EventsStack
from infra.task_processing_stack import TaskProcessingStack


def _create_stack(env_name: str = "dev") -> assertions.Template:
    """Helper to create a TaskProcessingStack and return the template."""
    app = cdk.App()
    config = get_environment_config(env_name)
    env = cdk.Environment(account="000000000000", region="us-east-1")

    database = DatabaseStack(
        app, "TestDatabase", config=config, env=env
    )
    events = EventsStack(
        app, "TestEvents", config=config, env=env
    )

    stack = TaskProcessingStack(
        app,
        "TestTaskProcessing",
        config=config,
        agents_table=database.agents_table,
        tasks_table=database.tasks_table,
        context_table=database.context_table,
        event_bus=events.event_bus,
        env=env,
    )
    return assertions.Template.from_stack(stack)


class TestTaskProcessingStackDev:
    """Tests for TaskProcessingStack in dev environment."""

    def test_lambda_function_created(self) -> None:
        template = _create_stack("dev")
        template.resource_count_is("AWS::Lambda::Function", 1)

    def test_lambda_runtime(self) -> None:
        template = _create_stack("dev")
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"Runtime": "python3.11"},
        )

    def test_lambda_handler(self) -> None:
        template = _create_stack("dev")
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"Handler": "runtime.handlers.task_processing.handler"},
        )

    def test_lambda_memory_size(self) -> None:
        template = _create_stack("dev")
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"MemorySize": 1024},
        )

    def test_lambda_timeout(self) -> None:
        template = _create_stack("dev")
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"Timeout": 300},
        )

    def test_lambda_environment_variables(self) -> None:
        template = _create_stack("dev")
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Environment": {
                    "Variables": {
                        "STAGE": "dev",
                    }
                }
            },
        )

    def test_ssm_parameter_created(self) -> None:
        template = _create_stack("dev")
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Description": "Task processing Lambda ARN"},
        )

    def test_outputs_created(self) -> None:
        template = _create_stack("dev")
        outputs = template.find_outputs("TaskProcessingFnArn")
        assert len(outputs) == 1

    def test_bedrock_iam_policy(self) -> None:
        template = _create_stack("dev")
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": {
                    "Statement": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Action": [
                                        "bedrock:InvokeModel",
                                        "bedrock:InvokeModelWithResponseStream",
                                    ],
                                    "Effect": "Allow",
                                }
                            )
                        ]
                    )
                }
            },
        )


class TestTaskProcessingStackProd:
    """Tests for TaskProcessingStack in prod environment."""

    def test_lambda_function_created(self) -> None:
        template = _create_stack("prod")
        template.resource_count_is("AWS::Lambda::Function", 1)

    def test_lambda_memory_size_prod(self) -> None:
        template = _create_stack("prod")
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"MemorySize": 1024},
        )
