"""Agent Management CDK stack for the Realtime Agentic API.

Provisions the Lambda function that handles agent CRUD operations,
with IAM permissions for DynamoDB (agents table) and EventBridge.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, Duration, Stack, Tags
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from infra.config import EnvironmentConfig


class AgentManagementStack(Stack):
    """Lambda function for agent CRUD with DynamoDB and EventBridge access."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: EnvironmentConfig,
        agents_table: dynamodb.ITable,
        event_bus: events.IEventBus,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._config = config

        for key, value in config.tags.items():
            Tags.of(self).add(key, value)

        # --- Lambda Function ---
        self.agent_management_fn = self._create_lambda(agents_table, event_bus)

        # --- SSM Parameters ---
        self._publish_ssm_params()

        # --- Outputs ---
        self._create_outputs()

    # Lambda

    def _create_lambda(
        self,
        agents_table: dynamodb.ITable,
        event_bus: events.IEventBus,
    ) -> _lambda.Function:
        """Create the Agent Management Lambda function."""
        fn = _lambda.Function(
            self,
            "AgentManagementFn",
            function_name=self._config.resource_name("agent-management"),
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="runtime.handlers.agent_management.handler",
            code=_lambda.Code.from_asset("."),
            memory_size=self._config.lambda_memory_mb,
            timeout=Duration.seconds(self._config.lambda_timeout_seconds),
            environment={
                "STAGE": self._config.stage,
                "AGENTS_TABLE": agents_table.table_name,
                "TASKS_TABLE": "",
                "CONTEXT_TABLE": "",
                "CONNECTIONS_TABLE": "",
                "EVENT_BUS_NAME": event_bus.event_bus_name,
            },
            description="Agent management CRUD operations",
        )

        # Grant DynamoDB read/write access to agents table
        agents_table.grant_read_write_data(fn)

        # Grant EventBridge put events
        event_bus.grant_put_events_to(fn)

        return fn

    # SSM Parameters

    def _publish_ssm_params(self) -> None:
        prefix = f"/{self._config.resource_prefix}"

        ssm.StringParameter(
            self,
            "SsmAgentManagementFnArn",
            parameter_name=f"{prefix}/agent-management-fn-arn",
            string_value=self.agent_management_fn.function_arn,
            description="Agent management Lambda ARN",
        )

    # Outputs

    def _create_outputs(self) -> None:
        CfnOutput(
            self,
            "AgentManagementFnArn",
            value=self.agent_management_fn.function_arn,
            description="Agent management Lambda ARN",
        )
        CfnOutput(
            self,
            "AgentManagementFnName",
            value=self.agent_management_fn.function_name,
            description="Agent management Lambda function name",
        )
