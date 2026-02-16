"""DynamoDB tables CDK stack for the Realtime Agentic API.

Defines four tables:
- Agents: Agent configurations with GSI for user-based queries
- Tasks: Task records with GSI for status-based queries
- Context: Conversation context with TTL for auto-expiration
- Connections: WebSocket connections with TTL for cleanup
"""

from __future__ import annotations

from aws_cdk import CfnOutput, RemovalPolicy, Stack, Tags
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from infra.config import EnvironmentConfig


class DatabaseStack(Stack):
    """DynamoDB tables and indexes for the Realtime Agentic API."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: EnvironmentConfig,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._config = config

        for key, value in config.tags.items():
            Tags.of(self).add(key, value)

        billing = (
            dynamodb.BillingMode.PAY_PER_REQUEST
            if config.dynamodb_billing_mode == "PAY_PER_REQUEST"
            else dynamodb.BillingMode.PROVISIONED
        )
        removal = (
            RemovalPolicy.DESTROY if config.stage == "dev" else RemovalPolicy.RETAIN
        )

        # --- Agents Table ---
        self.agents_table = self._create_agents_table(billing, removal)

        # --- Tasks Table ---
        self.tasks_table = self._create_tasks_table(billing, removal)

        # --- Context Table ---
        self.context_table = self._create_context_table(billing, removal)

        # --- Connections Table ---
        self.connections_table = self._create_connections_table(billing, removal)

        # --- SSM Parameters ---
        self._publish_ssm_params()

        # --- Outputs ---
        self._create_outputs()

    # ------------------------------------------------------------------
    # Agents Table
    # ------------------------------------------------------------------

    def _create_agents_table(
        self,
        billing: dynamodb.BillingMode,
        removal: RemovalPolicy,
    ) -> dynamodb.Table:
        """Create Agents table.

        Schema:
            PK: AGENT#<agentId>  SK: METADATA
        GSI1 (UserAgentsIndex):
            PK: USER#<userId>    SK: AGENT#<createdAt>
        """
        table = dynamodb.Table(
            self,
            "AgentsTable",
            table_name=self._config.resource_name("agents"),
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=billing,
            removal_policy=removal,
            point_in_time_recovery=self._config.stage != "dev",
        )

        table.add_global_secondary_index(
            index_name="UserAgentsIndex",
            partition_key=dynamodb.Attribute(
                name="GSI1PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        return table

    # ------------------------------------------------------------------
    # Tasks Table
    # ------------------------------------------------------------------

    def _create_tasks_table(
        self,
        billing: dynamodb.BillingMode,
        removal: RemovalPolicy,
    ) -> dynamodb.Table:
        """Create Tasks table.

        Schema:
            PK: AGENT#<agentId>  SK: TASK#<taskId>
        GSI1 (TaskStatusIndex):
            PK: TASK#<taskId>    SK: STATUS#<status>
        """
        table = dynamodb.Table(
            self,
            "TasksTable",
            table_name=self._config.resource_name("tasks"),
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=billing,
            removal_policy=removal,
            point_in_time_recovery=self._config.stage != "dev",
        )

        table.add_global_secondary_index(
            index_name="TaskStatusIndex",
            partition_key=dynamodb.Attribute(
                name="GSI1PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="GSI1SK", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        return table

    # ------------------------------------------------------------------
    # Context Table
    # ------------------------------------------------------------------

    def _create_context_table(
        self,
        billing: dynamodb.BillingMode,
        removal: RemovalPolicy,
    ) -> dynamodb.Table:
        """Create Context table with TTL for auto-expiration.

        Schema:
            PK: AGENT#<agentId>  SK: CONTEXT#<timestamp>
        TTL attribute: TTL (epoch seconds)
        """
        table = dynamodb.Table(
            self,
            "ContextTable",
            table_name=self._config.resource_name("context"),
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=billing,
            removal_policy=removal,
            time_to_live_attribute="TTL",
        )

        return table

    # ------------------------------------------------------------------
    # Connections Table
    # ------------------------------------------------------------------

    def _create_connections_table(
        self,
        billing: dynamodb.BillingMode,
        removal: RemovalPolicy,
    ) -> dynamodb.Table:
        """Create Connections table for WebSocket management.

        Schema:
            PK: CONNECTION#<connectionId>  SK: METADATA
        TTL attribute: TTL (epoch seconds)
        """
        table = dynamodb.Table(
            self,
            "ConnectionsTable",
            table_name=self._config.resource_name("connections"),
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=billing,
            removal_policy=removal,
            time_to_live_attribute="TTL",
        )

        return table

    # ------------------------------------------------------------------
    # SSM Parameters
    # ------------------------------------------------------------------

    def _publish_ssm_params(self) -> None:
        prefix = f"/{self._config.resource_prefix}"

        ssm.StringParameter(
            self,
            "SsmAgentsTableName",
            parameter_name=f"{prefix}/agents-table-name",
            string_value=self.agents_table.table_name,
            description="Agents DynamoDB table name",
        )

        ssm.StringParameter(
            self,
            "SsmTasksTableName",
            parameter_name=f"{prefix}/tasks-table-name",
            string_value=self.tasks_table.table_name,
            description="Tasks DynamoDB table name",
        )

        ssm.StringParameter(
            self,
            "SsmContextTableName",
            parameter_name=f"{prefix}/context-table-name",
            string_value=self.context_table.table_name,
            description="Context DynamoDB table name",
        )

        ssm.StringParameter(
            self,
            "SsmConnectionsTableName",
            parameter_name=f"{prefix}/connections-table-name",
            string_value=self.connections_table.table_name,
            description="Connections DynamoDB table name",
        )

        ssm.StringParameter(
            self,
            "SsmAgentsTableArn",
            parameter_name=f"{prefix}/agents-table-arn",
            string_value=self.agents_table.table_arn,
            description="Agents DynamoDB table ARN",
        )

        ssm.StringParameter(
            self,
            "SsmTasksTableArn",
            parameter_name=f"{prefix}/tasks-table-arn",
            string_value=self.tasks_table.table_arn,
            description="Tasks DynamoDB table ARN",
        )

        ssm.StringParameter(
            self,
            "SsmContextTableArn",
            parameter_name=f"{prefix}/context-table-arn",
            string_value=self.context_table.table_arn,
            description="Context DynamoDB table ARN",
        )

        ssm.StringParameter(
            self,
            "SsmConnectionsTableArn",
            parameter_name=f"{prefix}/connections-table-arn",
            string_value=self.connections_table.table_arn,
            description="Connections DynamoDB table ARN",
        )

    # ------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------

    def _create_outputs(self) -> None:
        CfnOutput(
            self,
            "AgentsTableName",
            value=self.agents_table.table_name,
            description="Agents DynamoDB table name",
        )
        CfnOutput(
            self,
            "TasksTableName",
            value=self.tasks_table.table_name,
            description="Tasks DynamoDB table name",
        )
        CfnOutput(
            self,
            "ContextTableName",
            value=self.context_table.table_name,
            description="Context DynamoDB table name",
        )
        CfnOutput(
            self,
            "ConnectionsTableName",
            value=self.connections_table.table_name,
            description="Connections DynamoDB table name",
        )
