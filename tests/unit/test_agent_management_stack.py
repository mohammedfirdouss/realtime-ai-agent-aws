"""Unit tests for the Agent Management CDK stack."""

import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk.assertions import Match, Template

from infra.agent_management_stack import AgentManagementStack
from infra.config import EnvironmentConfig


def _dev_config() -> EnvironmentConfig:
    return EnvironmentConfig(
        stage="dev",
        aws_account_id="123456789012",
        aws_region="us-east-1",
        nat_gateways=0,
        tags={"Environment": "dev"},
    )


def _synth_template(config: EnvironmentConfig | None = None) -> Template:
    config = config or _dev_config()
    app = cdk.App()
    env = cdk.Environment(account=config.aws_account_id, region=config.aws_region)

    # Create prerequisite resources in a support stack with same env
    support = cdk.Stack(app, "Support", env=env)
    table = dynamodb.Table(
        support,
        "AgentsTable",
        table_name="test-agents",
        partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
        sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
    )
    bus = events.EventBus(support, "EventBus", event_bus_name="test-events")

    stack = AgentManagementStack(
        app,
        "TestAgentManagement",
        config=config,
        agents_table=table,
        event_bus=bus,
        env=env,
    )
    return Template.from_stack(stack)


class TestAgentManagementStackLambda:
    """Test Lambda function resource creation."""

    def test_lambda_function_created(self):
        template = _synth_template()
        template.resource_count_is("AWS::Lambda::Function", 1)

    def test_lambda_runtime_python311(self):
        template = _synth_template()
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Runtime": "python3.11",
                "Handler": "runtime.handlers.agent_management.handler",
            },
        )

    def test_lambda_environment_variables(self):
        template = _synth_template()
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Environment": {
                    "Variables": Match.object_like(
                        {
                            "STAGE": "dev",
                            "EVENT_BUS_NAME": Match.any_value(),
                        }
                    )
                }
            },
        )

    def test_lambda_memory_and_timeout(self):
        config = _dev_config()
        template = _synth_template(config)
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "MemorySize": config.lambda_memory_mb,
                "Timeout": config.lambda_timeout_seconds,
            },
        )


class TestAgentManagementStackIAM:
    """Test IAM permissions."""

    def test_dynamodb_policy_exists(self):
        template = _synth_template()
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": Match.any_value(),
                                    "Effect": "Allow",
                                }
                            )
                        ]
                    )
                }
            },
        )


class TestAgentManagementStackOutputs:
    """Test stack outputs."""

    def test_function_arn_output(self):
        template = _synth_template()
        template.has_output(
            "AgentManagementFnArn",
            {"Description": "Agent management Lambda ARN"},
        )

    def test_function_name_output(self):
        template = _synth_template()
        template.has_output(
            "AgentManagementFnName",
            {"Description": "Agent management Lambda function name"},
        )


class TestAgentManagementStackSSM:
    """Test SSM parameter creation."""

    def test_ssm_parameter_created(self):
        template = _synth_template()
        template.resource_count_is("AWS::SSM::Parameter", 1)
