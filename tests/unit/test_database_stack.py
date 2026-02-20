"""Unit tests for the Database CDK stack."""

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infra.config import EnvironmentConfig
from infra.database_stack import DatabaseStack


def _synth_template(config: EnvironmentConfig) -> Template:
    app = cdk.App()
    stack = DatabaseStack(
        app,
        "TestDatabase",
        config=config,
        env=cdk.Environment(account=config.aws_account_id, region=config.aws_region),
    )
    return Template.from_stack(stack)
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
        tags={"Environment": "prod"},
    )
class TestDatabaseStackTables:
    """Tests that all four DynamoDB tables are created."""

    def test_four_tables_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::DynamoDB::Table", 4)

    def test_agents_table_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"TableName": "realtime-agentic-api-dev-agents"},
        )

    def test_tasks_table_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"TableName": "realtime-agentic-api-dev-tasks"},
        )

    def test_context_table_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"TableName": "realtime-agentic-api-dev-context"},
        )

    def test_connections_table_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {"TableName": "realtime-agentic-api-dev-connections"},
        )
class TestDatabaseStackKeySchema:
    """Tests for partition and sort key configuration."""

    def test_agents_table_key_schema(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "realtime-agentic-api-dev-agents",
                "KeySchema": [
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
            },
        )

    def test_tasks_table_key_schema(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "realtime-agentic-api-dev-tasks",
                "KeySchema": [
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
            },
        )

    def test_context_table_key_schema(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "realtime-agentic-api-dev-context",
                "KeySchema": [
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
            },
        )

    def test_connections_table_key_schema(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "realtime-agentic-api-dev-connections",
                "KeySchema": [
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
            },
        )
class TestDatabaseStackGSIs:
    """Tests for Global Secondary Indexes."""

    def test_agents_table_has_user_agents_gsi(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "realtime-agentic-api-dev-agents",
                "GlobalSecondaryIndexes": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "IndexName": "UserAgentsIndex",
                                "KeySchema": [
                                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                                ],
                                "Projection": {"ProjectionType": "ALL"},
                            }
                        )
                    ]
                ),
            },
        )

    def test_tasks_table_has_task_status_gsi(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "realtime-agentic-api-dev-tasks",
                "GlobalSecondaryIndexes": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "IndexName": "TaskStatusIndex",
                                "KeySchema": [
                                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                                ],
                                "Projection": {"ProjectionType": "ALL"},
                            }
                        )
                    ]
                ),
            },
        )
class TestDatabaseStackTTL:
    """Tests for TTL configuration."""

    def test_context_table_has_ttl(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "realtime-agentic-api-dev-context",
                "TimeToLiveSpecification": {
                    "AttributeName": "TTL",
                    "Enabled": True,
                },
            },
        )

    def test_connections_table_has_ttl(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "realtime-agentic-api-dev-connections",
                "TimeToLiveSpecification": {
                    "AttributeName": "TTL",
                    "Enabled": True,
                },
            },
        )
class TestDatabaseStackBilling:
    """Tests for billing mode configuration."""

    def test_pay_per_request_billing(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "realtime-agentic-api-dev-agents",
                "BillingMode": "PAY_PER_REQUEST",
            },
        )
class TestDatabaseStackDevRemovalPolicy:
    """Tests that dev tables use DESTROY removal policy."""

    def test_dev_tables_deleted_on_stack_removal(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource(
            "AWS::DynamoDB::Table",
            {
                "DeletionPolicy": "Delete",
                "UpdateReplacePolicy": "Delete",
            },
        )
class TestDatabaseStackProd:
    """Tests for production-specific configuration."""

    def test_prod_tables_retained(self) -> None:
        template = _synth_template(_prod_config())
        template.has_resource(
            "AWS::DynamoDB::Table",
            {
                "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain",
            },
        )

    def test_prod_pitr_enabled(self) -> None:
        template = _synth_template(_prod_config())
        template.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": "realtime-agentic-api-prod-agents",
                "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
            },
        )
class TestDatabaseStackSSMParams:
    """Tests for SSM parameter publishing."""

    def test_ssm_parameters_created(self) -> None:
        template = _synth_template(_dev_config())
        # 4 table names + 4 table ARNs = 8
        template.resource_count_is("AWS::SSM::Parameter", 8)
class TestDatabaseStackOutputs:
    """Tests for stack outputs."""

    def test_outputs_present(self) -> None:
        template = _synth_template(_dev_config())
        template.has_output("AgentsTableName", {})
        template.has_output("TasksTableName", {})
        template.has_output("ContextTableName", {})
        template.has_output("ConnectionsTableName", {})
