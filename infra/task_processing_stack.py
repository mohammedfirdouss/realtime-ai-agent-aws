"""Task Processing CDK stack for the Realtime Agentic API.

Provisions the Lambda function that processes tasks using the Strands Agent
framework, with IAM permissions for DynamoDB, EventBridge, and Bedrock.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, Duration, Stack, Tags
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from infra.config import EnvironmentConfig


class TaskProcessingStack(Stack):
    """Lambda function for task processing with Strands Agent integration."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: EnvironmentConfig,
        agents_table: dynamodb.ITable,
        tasks_table: dynamodb.ITable,
        context_table: dynamodb.ITable,
        event_bus: events.IEventBus,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._config = config

        for key, value in config.tags.items():
            Tags.of(self).add(key, value)

        # --- Lambda Function ---
        self.task_processing_fn = self._create_lambda(
            agents_table, tasks_table, context_table, event_bus
        )

        # --- SSM Parameters ---
        self._publish_ssm_params()

        # --- Outputs ---
        self._create_outputs()

    def _create_lambda(
        self,
        agents_table: dynamodb.ITable,
        tasks_table: dynamodb.ITable,
        context_table: dynamodb.ITable,
        event_bus: events.IEventBus,
    ) -> _lambda.Function:
        """Create the Task Processing Lambda function."""
        fn = _lambda.Function(
            self,
            "TaskProcessingFn",
            function_name=self._config.resource_name("task-processing"),
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="runtime.handlers.task_processing.handler",
            code=_lambda.Code.from_asset("."),
            memory_size=self._config.task_lambda_memory_mb,
            timeout=Duration.seconds(self._config.task_lambda_timeout_seconds),
            environment={
                "STAGE": self._config.stage,
                "AGENTS_TABLE": agents_table.table_name,
                "TASKS_TABLE": tasks_table.table_name,
                "CONTEXT_TABLE": context_table.table_name,
                "CONNECTIONS_TABLE": "",
                "EVENT_BUS_NAME": event_bus.event_bus_name,
            },
            description="Task processing with Strands Agent framework",
        )

        # Grant DynamoDB read/write access
        agents_table.grant_read_write_data(fn)
        tasks_table.grant_read_write_data(fn)
        context_table.grant_read_write_data(fn)

        # Grant EventBridge put events
        event_bus.grant_put_events_to(fn)

        # Grant Bedrock model invocation access
        fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["arn:aws:bedrock:*::foundation-model/*"],
            )
        )

        # Grant Secrets Manager access for LLM API keys
        fn.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                ],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:{self._config.secrets_prefix}*"
                ],
            )
        )

        return fn

    def _publish_ssm_params(self) -> None:
        prefix = f"/{self._config.resource_prefix}"

        ssm.StringParameter(
            self,
            "SsmTaskProcessingFnArn",
            parameter_name=f"{prefix}/task-processing-fn-arn",
            string_value=self.task_processing_fn.function_arn,
            description="Task processing Lambda ARN",
        )

    def _create_outputs(self) -> None:
        CfnOutput(
            self,
            "TaskProcessingFnArn",
            value=self.task_processing_fn.function_arn,
            description="Task processing Lambda ARN",
        )
        CfnOutput(
            self,
            "TaskProcessingFnName",
            value=self.task_processing_fn.function_name,
            description="Task processing Lambda function name",
        )
