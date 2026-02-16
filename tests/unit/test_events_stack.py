"""Unit tests for the Events CDK stack."""

import aws_cdk as cdk
from aws_cdk.assertions import Template

from infra.config import EnvironmentConfig
from infra.events_stack import EventsStack


def _synth_template(config: EnvironmentConfig) -> Template:
    app = cdk.App()
    stack = EventsStack(
        app,
        "TestEvents",
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


class TestEventsStackBus:
    """Tests for the EventBridge bus creation."""

    def test_event_bus_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::Events::EventBus", 1)

    def test_event_bus_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Events::EventBus",
            {"Name": "realtime-agentic-api-dev-events"},
        )

    def test_prod_event_bus_name(self) -> None:
        template = _synth_template(_prod_config())
        template.has_resource_properties(
            "AWS::Events::EventBus",
            {"Name": "realtime-agentic-api-prod-events"},
        )


class TestEventsStackArchive:
    """Tests for event archive configuration."""

    def test_archive_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::Events::Archive", 1)

    def test_archive_name(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Events::Archive",
            {"ArchiveName": "realtime-agentic-api-dev-event-archive"},
        )

    def test_dev_archive_retention_7_days(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Events::Archive",
            {"RetentionDays": 7},
        )

    def test_prod_archive_retention_30_days(self) -> None:
        template = _synth_template(_prod_config())
        template.has_resource_properties(
            "AWS::Events::Archive",
            {"RetentionDays": 30},
        )


class TestEventsStackRules:
    """Tests for event rules."""

    def test_five_rules_created(self) -> None:
        template = _synth_template(_dev_config())
        template.resource_count_is("AWS::Events::Rule", 5)

    def test_agent_events_rule(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Events::Rule",
            {
                "Name": "realtime-agentic-api-dev-agent-events",
                "EventPattern": {
                    "source": ["realtime-agentic-api.agents"],
                    "detail-type": ["AgentCreated", "AgentDeleted"],
                },
            },
        )

    def test_task_events_rule(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Events::Rule",
            {
                "Name": "realtime-agentic-api-dev-task-events",
                "EventPattern": {
                    "source": ["realtime-agentic-api.tasks"],
                    "detail-type": ["TaskCreated", "TaskCompleted", "TaskProgress"],
                },
            },
        )

    def test_status_events_rule(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Events::Rule",
            {
                "Name": "realtime-agentic-api-dev-status-events",
                "EventPattern": {
                    "source": ["realtime-agentic-api.status"],
                    "detail-type": ["AgentStatusChanged"],
                },
            },
        )

    def test_error_events_rule(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Events::Rule",
            {
                "Name": "realtime-agentic-api-dev-error-events",
                "EventPattern": {
                    "source": ["realtime-agentic-api.errors"],
                    "detail-type": ["ErrorOccurred"],
                },
            },
        )

    def test_scheduler_events_rule(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::Events::Rule",
            {
                "Name": "realtime-agentic-api-dev-scheduler-events",
                "EventPattern": {
                    "source": ["realtime-agentic-api.scheduler"],
                    "detail-type": ["ScheduledTask"],
                },
            },
        )


class TestEventsStackSSMParams:
    """Tests for SSM parameter publishing."""

    def test_ssm_parameters_created(self) -> None:
        template = _synth_template(_dev_config())
        # event bus name + event bus ARN = 2
        template.resource_count_is("AWS::SSM::Parameter", 2)

    def test_event_bus_name_param(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/realtime-agentic-api-dev/event-bus-name",
                "Type": "String",
            },
        )

    def test_event_bus_arn_param(self) -> None:
        template = _synth_template(_dev_config())
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Name": "/realtime-agentic-api-dev/event-bus-arn",
                "Type": "String",
            },
        )


class TestEventsStackOutputs:
    """Tests for stack outputs."""

    def test_outputs_present(self) -> None:
        template = _synth_template(_dev_config())
        template.has_output("EventBusName", {})
        template.has_output("EventBusArn", {})
