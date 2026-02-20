"""Unit tests for the EventPublisher."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from runtime.shared.config import RuntimeConfig
from runtime.shared.event_publisher import EventPublisher, EventValidationError


def _config() -> RuntimeConfig:
    return RuntimeConfig(
        stage="dev",
        aws_region="us-east-1",
        agents_table="agents",
        tasks_table="tasks",
        context_table="context",
        connections_table="connections",
        event_bus_name="test-events",
        secrets_prefix="test",
    )
def _mock_client() -> MagicMock:
    """Return a mock boto3 events client with a successful put_events response."""
    client = MagicMock()
    client.put_events.return_value = {
        "FailedEntryCount": 0,
        "Entries": [{"EventId": "test-event-id-123"}],
    }
    return client
def _publisher(client: MagicMock) -> EventPublisher:
    """Create an EventPublisher with a pre-configured mock client."""
    with patch("runtime.shared.event_publisher.boto3") as mock_boto:
        mock_boto.client.return_value = client
        pub = EventPublisher(_config())
    return pub
def _last_put_entry(client: MagicMock) -> dict[str, Any]:
    """Extract the single entry from the most recent put_events call."""
    call_kwargs = client.put_events.call_args[1]
    return call_kwargs["Entries"][0]
class TestEventPublisherAgentCreated:
    """Tests for publish_agent_created."""

    def test_success(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        event_id = pub.publish_agent_created("agent-1", "user-1", "My Agent")

        assert event_id == "test-event-id-123"
        entry = _last_put_entry(client)
        assert entry["Source"] == "realtime-agentic-api.agents"
        assert entry["DetailType"] == "AgentCreated"
        assert entry["EventBusName"] == "test-events"
        detail = json.loads(entry["Detail"])
        assert detail["agentId"] == "agent-1"
        assert detail["userId"] == "user-1"
        assert detail["agentName"] == "My Agent"
        assert "timestamp" in detail

    def test_with_metadata(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        pub.publish_agent_created("a", "u", "n", metadata={"model": "gpt-4"})

        detail = json.loads(_last_put_entry(client)["Detail"])
        assert detail["metadata"] == {"model": "gpt-4"}

    def test_empty_agent_id_raises(self) -> None:
        pub = _publisher(_mock_client())
        with pytest.raises(EventValidationError, match="agent_id"):
            pub.publish_agent_created("", "user-1", "name")

    def test_blank_agent_id_raises(self) -> None:
        pub = _publisher(_mock_client())
        with pytest.raises(EventValidationError, match="agent_id"):
            pub.publish_agent_created("   ", "user-1", "name")
class TestEventPublisherAgentDeleted:
    """Tests for publish_agent_deleted."""

    def test_success(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        event_id = pub.publish_agent_deleted("agent-1", "user-1")

        assert event_id == "test-event-id-123"
        entry = _last_put_entry(client)
        assert entry["DetailType"] == "AgentDeleted"
        detail = json.loads(entry["Detail"])
        assert detail["agentId"] == "agent-1"
        assert detail["userId"] == "user-1"
class TestEventPublisherTaskCreated:
    """Tests for publish_task_created."""

    def test_success(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        pub.publish_task_created("task-1", "agent-1", "Do something")

        entry = _last_put_entry(client)
        assert entry["Source"] == "realtime-agentic-api.tasks"
        assert entry["DetailType"] == "TaskCreated"
        detail = json.loads(entry["Detail"])
        assert detail["taskId"] == "task-1"
        assert detail["description"] == "Do something"

    def test_empty_description_raises(self) -> None:
        pub = _publisher(_mock_client())
        with pytest.raises(EventValidationError, match="description"):
            pub.publish_task_created("t", "a", "")
class TestEventPublisherTaskCompleted:
    """Tests for publish_task_completed."""

    def test_success(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        pub.publish_task_completed("task-1", "agent-1", "completed")

        detail = json.loads(_last_put_entry(client)["Detail"])
        assert detail["status"] == "completed"

    def test_with_result(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        pub.publish_task_completed("t", "a", "completed", result={"output": "done"})

        detail = json.loads(_last_put_entry(client)["Detail"])
        assert detail["result"] == {"output": "done"}

    def test_invalid_status_raises(self) -> None:
        pub = _publisher(_mock_client())
        with pytest.raises(EventValidationError, match="Invalid task status"):
            pub.publish_task_completed("t", "a", "invalid-status")
class TestEventPublisherTaskProgress:
    """Tests for publish_task_progress."""

    def test_success(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        pub.publish_task_progress("task-1", "agent-1", 50)

        entry = _last_put_entry(client)
        assert entry["DetailType"] == "TaskProgress"
        detail = json.loads(entry["Detail"])
        assert detail["progressPct"] == 50

    def test_with_message(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        pub.publish_task_progress("t", "a", 75, message="almost done")

        detail = json.loads(_last_put_entry(client)["Detail"])
        assert detail["message"] == "almost done"

    def test_negative_progress_raises(self) -> None:
        pub = _publisher(_mock_client())
        with pytest.raises(EventValidationError, match="progress_pct"):
            pub.publish_task_progress("t", "a", -1)

    def test_over_100_progress_raises(self) -> None:
        pub = _publisher(_mock_client())
        with pytest.raises(EventValidationError, match="progress_pct"):
            pub.publish_task_progress("t", "a", 101)

    def test_boundary_0_accepted(self) -> None:
        client = _mock_client()
        pub = _publisher(client)
        pub.publish_task_progress("t", "a", 0)
        detail = json.loads(_last_put_entry(client)["Detail"])
        assert detail["progressPct"] == 0

    def test_boundary_100_accepted(self) -> None:
        client = _mock_client()
        pub = _publisher(client)
        pub.publish_task_progress("t", "a", 100)
        detail = json.loads(_last_put_entry(client)["Detail"])
        assert detail["progressPct"] == 100
class TestEventPublisherStatusChanged:
    """Tests for publish_status_changed."""

    def test_success(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        pub.publish_status_changed("agent-1", "idle", "processing")

        entry = _last_put_entry(client)
        assert entry["Source"] == "realtime-agentic-api.status"
        assert entry["DetailType"] == "AgentStatusChanged"
        detail = json.loads(entry["Detail"])
        assert detail["previousStatus"] == "idle"
        assert detail["newStatus"] == "processing"

    def test_invalid_previous_status_raises(self) -> None:
        pub = _publisher(_mock_client())
        with pytest.raises(EventValidationError, match="previous_status"):
            pub.publish_status_changed("a", "bogus", "idle")

    def test_invalid_new_status_raises(self) -> None:
        pub = _publisher(_mock_client())
        with pytest.raises(EventValidationError, match="new_status"):
            pub.publish_status_changed("a", "idle", "bogus")
class TestEventPublisherErrorOccurred:
    """Tests for publish_error_occurred."""

    def test_success(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        pub.publish_error_occurred("LLM_TIMEOUT", "Model timed out")

        entry = _last_put_entry(client)
        assert entry["Source"] == "realtime-agentic-api.errors"
        assert entry["DetailType"] == "ErrorOccurred"
        detail = json.loads(entry["Detail"])
        assert detail["errorCode"] == "LLM_TIMEOUT"
        assert detail["errorMessage"] == "Model timed out"

    def test_with_agent_and_task(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        pub.publish_error_occurred(
            "ERR", "msg", agent_id="a1", task_id="t1", metadata={"extra": "info"}
        )

        detail = json.loads(_last_put_entry(client)["Detail"])
        assert detail["agentId"] == "a1"
        assert detail["taskId"] == "t1"
        assert detail["metadata"] == {"extra": "info"}
class TestEventPublisherScheduledTask:
    """Tests for publish_scheduled_task."""

    def test_success(self) -> None:
        client = _mock_client()
        pub = _publisher(client)

        pub.publish_scheduled_task("task-1", "agent-1", "rate(1 hour)")

        entry = _last_put_entry(client)
        assert entry["Source"] == "realtime-agentic-api.scheduler"
        assert entry["DetailType"] == "ScheduledTask"
        detail = json.loads(entry["Detail"])
        assert detail["scheduleExpression"] == "rate(1 hour)"
class TestEventPublisherFailedEntry:
    """Tests for handling EventBridge failures."""

    def test_failed_entry_raises(self) -> None:
        client = _mock_client()
        client.put_events.return_value = {
            "FailedEntryCount": 1,
            "Entries": [{"ErrorCode": "InternalError", "ErrorMessage": "Boom"}],
        }
        pub = _publisher(client)

        with pytest.raises(RuntimeError, match="Failed to publish event"):
            pub.publish_agent_created("a", "u", "n")
