"""EventBridge CDK stack for the Realtime Agentic API.

Defines the custom event bus, event rules, and routing configuration
for all event types in the system.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_events as events
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from infra.config import EnvironmentConfig


class EventsStack(Stack):
    """EventBridge bus and rules for the Realtime Agentic API."""

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

        # --- Event Bus ---
        self.event_bus = self._create_event_bus()

        # --- Event Rules ---
        self.agent_events_rule = self._create_agent_events_rule()
        self.task_events_rule = self._create_task_events_rule()
        self.status_events_rule = self._create_status_events_rule()
        self.error_events_rule = self._create_error_events_rule()
        self.scheduler_events_rule = self._create_scheduler_events_rule()

        # --- SSM Parameters ---
        self._publish_ssm_params()

        # --- Outputs ---
        self._create_outputs()

    # Event Bus

    def _create_event_bus(self) -> events.EventBus:
        """Create custom EventBridge event bus."""
        bus = events.EventBus(
            self,
            "EventBus",
            event_bus_name=self._config.resource_name("events"),
        )

        if self._config.stage == "dev":
            bus.apply_removal_policy(RemovalPolicy.DESTROY)
        else:
            bus.apply_removal_policy(RemovalPolicy.RETAIN)

        # Archive all events for replay / debugging
        bus.archive(
            "EventArchive",
            archive_name=self._config.resource_name("event-archive"),
            description=f"Archive for {self._config.stage} events",
            retention=Duration.days(7)
            if self._config.stage == "dev"
            else Duration.days(30),
            event_pattern=events.EventPattern(
                source=[events.Match.prefix("realtime-agentic-api")],
            ),
        )

        return bus

    # Event Rules

    def _create_agent_events_rule(self) -> events.Rule:
        """Rule matching AgentCreated and AgentDeleted events."""
        return events.Rule(
            self,
            "AgentEventsRule",
            rule_name=self._config.resource_name("agent-events"),
            description="Routes agent lifecycle events",
            event_bus=self.event_bus,
            event_pattern=events.EventPattern(
                source=["realtime-agentic-api.agents"],
                detail_type=["AgentCreated", "AgentDeleted"],
            ),
        )

    def _create_task_events_rule(self) -> events.Rule:
        """Rule matching TaskCreated, TaskCompleted, and TaskProgress events."""
        return events.Rule(
            self,
            "TaskEventsRule",
            rule_name=self._config.resource_name("task-events"),
            description="Routes task lifecycle events",
            event_bus=self.event_bus,
            event_pattern=events.EventPattern(
                source=["realtime-agentic-api.tasks"],
                detail_type=["TaskCreated", "TaskCompleted", "TaskProgress"],
            ),
        )

    def _create_status_events_rule(self) -> events.Rule:
        """Rule matching AgentStatusChanged events."""
        return events.Rule(
            self,
            "StatusEventsRule",
            rule_name=self._config.resource_name("status-events"),
            description="Routes agent status change events",
            event_bus=self.event_bus,
            event_pattern=events.EventPattern(
                source=["realtime-agentic-api.status"],
                detail_type=["AgentStatusChanged"],
            ),
        )

    def _create_error_events_rule(self) -> events.Rule:
        """Rule matching ErrorOccurred events."""
        return events.Rule(
            self,
            "ErrorEventsRule",
            rule_name=self._config.resource_name("error-events"),
            description="Routes error events",
            event_bus=self.event_bus,
            event_pattern=events.EventPattern(
                source=["realtime-agentic-api.errors"],
                detail_type=["ErrorOccurred"],
            ),
        )

    def _create_scheduler_events_rule(self) -> events.Rule:
        """Rule matching ScheduledTask events."""
        return events.Rule(
            self,
            "SchedulerEventsRule",
            rule_name=self._config.resource_name("scheduler-events"),
            description="Routes scheduled task events",
            event_bus=self.event_bus,
            event_pattern=events.EventPattern(
                source=["realtime-agentic-api.scheduler"],
                detail_type=["ScheduledTask"],
            ),
        )

    # SSM Parameters

    def _publish_ssm_params(self) -> None:
        prefix = f"/{self._config.resource_prefix}"

        ssm.StringParameter(
            self,
            "SsmEventBusName",
            parameter_name=f"{prefix}/event-bus-name",
            string_value=self.event_bus.event_bus_name,
            description="EventBridge event bus name",
        )

        ssm.StringParameter(
            self,
            "SsmEventBusArn",
            parameter_name=f"{prefix}/event-bus-arn",
            string_value=self.event_bus.event_bus_arn,
            description="EventBridge event bus ARN",
        )

    # Outputs

    def _create_outputs(self) -> None:
        CfnOutput(
            self,
            "EventBusName",
            value=self.event_bus.event_bus_name,
            description="EventBridge event bus name",
        )
        CfnOutput(
            self,
            "EventBusArn",
            value=self.event_bus.event_bus_arn,
            description="EventBridge event bus ARN",
        )
