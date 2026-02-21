"""Tests for infra.task_processing_stack CDK stack."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk.assertions import Match, Template

from infra.config import EnvironmentConfig
from infra.task_processing_stack import TaskProcessingStack


def _dev_config() -> EnvironmentConfig:
    return EnvironmentConfig(
        stage="dev",
        aws_account_id="123456789012",
        aws_region="us-east-1",
        nat_gateways=0,
        tags={"Environment": "dev"},
    )


def _prod_config() -> EnvironmentConfig:
    return EnvironmentConfig(
        stage="prod",
        aws_account_id="123456789012",
        aws_region="us-east-1",
        max_azs=3,
        nat_gateways=2,
        lambda_memory_mb=512,
        tags={"Environment": "prod"},
    )


def _synth_template(config: EnvironmentConfig | None = None) -> Template:
    config = config or _dev_config()
    app = cdk.App()
    env = cdk.Environment(account=config.aws_account_id, region=config.aws_region)

    support = cdk.Stack(app, "Support", env=env)
    agents_table = dynamodb.Table(
        support,
        "AgentsTable",
        table_name="test-agents",
        partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
        sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
    )
    tasks_table = dynamodb.Table(
        support,
        "TasksTable",
        table_name="test-tasks",
        partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
        sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
    )
    context_table = dynamodb.Table(
        support,
        "ContextTable",
        table_name="test-context",
        partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
        sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
    )
    bus = events.EventBus(support, "EventBus", event_bus_name="test-events")

    stack = TaskProcessingStack(
        app,
        "TestTaskProcessing",
        config=config,
        agents_table=agents_table,
        tasks_table=tasks_table,
        context_table=context_table,
        event_bus=bus,
        env=env,
    )
    return Template.from_stack(stack)


class TestTaskProcessingStackDev:
    """Tests for TaskProcessingStack in dev environment."""

    def test_lambda_function_created(self) -> None:
        template = _synth_template()
        template.resource_count_is("AWS::Lambda::Function", 1)

    def test_lambda_runtime(self) -> None:
        template = _synth_template()
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"Runtime": "python3.11"},
        )

    def test_lambda_handler(self) -> None:
        template = _synth_template()
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"Handler": "runtime.handlers.task_processing.handler"},
        )

    def test_lambda_memory_size(self) -> None:
        template = _synth_template()
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"MemorySize": 1024},
        )

    def test_lambda_timeout(self) -> None:
        template = _synth_template()
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"Timeout": 300},
        )

    def test_lambda_environment_variables(self) -> None:
        template = _synth_template()
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
        template = _synth_template()
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {"Description": "Task processing Lambda ARN"},
        )

    def test_outputs_created(self) -> None:
        template = _synth_template()
        outputs = template.find_outputs("TaskProcessingFnArn")
        assert len(outputs) == 1

    def test_bedrock_iam_policy(self) -> None:
        template = _synth_template()
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
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
        template = _synth_template(_prod_config())
        template.resource_count_is("AWS::Lambda::Function", 1)

    def test_lambda_memory_size_prod(self) -> None:
        template = _synth_template(_prod_config())
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {"MemorySize": 1024},
        )
