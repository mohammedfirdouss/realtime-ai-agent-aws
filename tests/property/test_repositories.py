"""Property-based tests for the data access layer using Hypothesis + moto.

Tests validate correctness properties from the design document (Properties 61-65).
Each test runs with at least 100 randomized inputs.
"""

from __future__ import annotations

import boto3
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from runtime.repositories.agent_repository import AgentRepository
from runtime.repositories.base_repository import ConditionalCheckError, ItemNotFoundError
from runtime.repositories.connection_repository import ConnectionRepository
from runtime.repositories.context_repository import ContextRepository
from runtime.repositories.task_repository import TaskRepository

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_safe_text = st.text(
    alphabet=st.characters(
        categories=("L", "N", "P", "Z"),
        exclude_characters="\x00",
    ),
    min_size=1,
    max_size=100,
)

_user_id = _safe_text.filter(lambda s: s.strip() != "")
_agent_name = _safe_text.filter(lambda s: s.strip() != "")

_llm_provider = st.sampled_from(["openai", "anthropic"])

_agent_config = st.fixed_dictionaries(
    {
        "llmProvider": _llm_provider,
        "model": st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_."),
        "tools": st.just([]),
    },
    optional={
        "systemPrompt": st.text(min_size=0, max_size=200),
    },
)

_task_description = st.text(
    min_size=1,
    max_size=500,
    alphabet=st.characters(categories=("L", "N", "P", "Z"), exclude_characters="\x00"),
)

_message = st.fixed_dictionaries(
    {
        "role": st.sampled_from(["user", "assistant", "system", "tool"]),
        "content": st.text(min_size=1, max_size=200),
        "timestamp": st.just("2025-01-01T00:00:00+00:00"),
    }
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

AGENTS_TABLE = "test-agents"
TASKS_TABLE = "test-tasks"
CONTEXT_TABLE = "test-context"
CONNECTIONS_TABLE = "test-connections"


def _create_tables() -> None:
    """Create all four DynamoDB tables in moto."""
    client = boto3.client("dynamodb", region_name="us-east-1")

    # Agents table + GSI
    client.create_table(
        TableName=AGENTS_TABLE,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "UserAgentsIndex",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Tasks table + GSI
    client.create_table(
        TableName=TASKS_TABLE,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "TaskStatusIndex",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Context table
    client.create_table(
        TableName=CONTEXT_TABLE,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Connections table
    client.create_table(
        TableName=CONNECTIONS_TABLE,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def _agent_repo() -> AgentRepository:
    return AgentRepository(AGENTS_TABLE, region="us-east-1")


def _task_repo() -> TaskRepository:
    return TaskRepository(TASKS_TABLE, region="us-east-1")


def _context_repo() -> ContextRepository:
    return ContextRepository(CONTEXT_TABLE, region="us-east-1")


def _connection_repo() -> ConnectionRepository:
    return ConnectionRepository(CONNECTIONS_TABLE, region="us-east-1")


# ---------------------------------------------------------------------------
# Property 61: Agent creation with unique ID
# For any created agent, the agent should be stored in DynamoDB with a unique ID.
# Feature: realtime-agentic-api, Property 61
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestProperty61AgentCreationUniqueId:

    @settings(max_examples=100, deadline=None)
    @given(user_id=_user_id, name=_agent_name, config=_agent_config)
    def test_agent_created_has_unique_id(
        self, user_id: str, name: str, config: dict
    ) -> None:
        with mock_aws():
            _create_tables()
            repo = _agent_repo()

            agent = repo.create_agent(user_id=user_id, name=name, configuration=config)

            assert "agentId" in agent
            assert len(agent["agentId"]) > 0

            # Retrieve and verify
            retrieved = repo.get_agent(agent["agentId"])
            assert retrieved["agentId"] == agent["agentId"]
            assert retrieved["userId"] == user_id
            assert retrieved["name"] == name

    @settings(max_examples=100, deadline=None)
    @given(user_id=_user_id, name=_agent_name, config=_agent_config)
    def test_duplicate_agent_id_rejected(
        self, user_id: str, name: str, config: dict
    ) -> None:
        with mock_aws():
            _create_tables()
            repo = _agent_repo()

            agent = repo.create_agent(user_id=user_id, name=name, configuration=config)

            with pytest.raises(ConditionalCheckError):
                repo.create_agent(
                    user_id=user_id,
                    name=name,
                    configuration=config,
                    agent_id=agent["agentId"],
                )


# ---------------------------------------------------------------------------
# Property 62: State update persistence
# For any agent state change, the corresponding DynamoDB record should be updated.
# Feature: realtime-agentic-api, Property 62
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestProperty62StateUpdatePersistence:

    @settings(max_examples=100, deadline=None)
    @given(
        user_id=_user_id,
        name=_agent_name,
        config=_agent_config,
        new_status=st.sampled_from(["idle", "processing", "waiting", "error"]),
    )
    def test_status_update_persisted(
        self, user_id: str, name: str, config: dict, new_status: str
    ) -> None:
        with mock_aws():
            _create_tables()
            repo = _agent_repo()

            agent = repo.create_agent(user_id=user_id, name=name, configuration=config)
            repo.update_agent_status(agent["agentId"], new_status)

            retrieved = repo.get_agent(agent["agentId"])
            assert retrieved["status"] == new_status

    @settings(max_examples=100, deadline=None)
    @given(
        user_id=_user_id,
        name=_agent_name,
        config=_agent_config,
        new_name=_agent_name,
    )
    def test_name_update_persisted(
        self, user_id: str, name: str, config: dict, new_name: str
    ) -> None:
        with mock_aws():
            _create_tables()
            repo = _agent_repo()

            agent = repo.create_agent(user_id=user_id, name=name, configuration=config)
            repo.update_agent(agent["agentId"], updates={"name": new_name})

            retrieved = repo.get_agent(agent["agentId"])
            assert retrieved["name"] == new_name


# ---------------------------------------------------------------------------
# Property 63: Task persistence
# For any created task, the task details should be stored in DynamoDB.
# Feature: realtime-agentic-api, Property 63
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestProperty63TaskPersistence:

    @settings(max_examples=100, deadline=None)
    @given(description=_task_description)
    def test_task_created_and_retrievable(self, description: str) -> None:
        with mock_aws():
            _create_tables()
            repo = _task_repo()

            agent_id = "agent-test-001"
            task = repo.create_task(agent_id=agent_id, description=description)

            assert "taskId" in task
            assert task["agentId"] == agent_id
            assert task["description"] == description
            assert task["status"] == "pending"

            retrieved = repo.get_task(agent_id, task["taskId"])
            assert retrieved["taskId"] == task["taskId"]
            assert retrieved["description"] == description

    @settings(max_examples=100, deadline=None)
    @given(
        description=_task_description,
        new_status=st.sampled_from(["running", "completed", "failed", "cancelled"]),
    )
    def test_task_status_update_persisted(self, description: str, new_status: str) -> None:
        with mock_aws():
            _create_tables()
            repo = _task_repo()

            agent_id = "agent-test-002"
            task = repo.create_task(agent_id=agent_id, description=description)

            updated = repo.update_task_status(agent_id, task["taskId"], new_status)
            assert updated["status"] == new_status

            retrieved = repo.get_task(agent_id, task["taskId"])
            assert retrieved["status"] == new_status

            if new_status in ("completed", "failed", "cancelled"):
                assert "completedAt" in retrieved


# ---------------------------------------------------------------------------
# Property 64: Conversation history append
# For any conversation turn, the new turn should be appended to the
# conversation history in DynamoDB.
# Feature: realtime-agentic-api, Property 64
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestProperty64ConversationHistoryAppend:

    @settings(max_examples=100, deadline=None)
    @given(messages=st.lists(_message, min_size=1, max_size=5))
    def test_messages_appended_to_history(self, messages: list[dict]) -> None:
        with mock_aws():
            _create_tables()
            repo = _context_repo()

            agent_id = "agent-context-001"
            ctx = repo.append_messages(agent_id, messages)

            latest = repo.get_latest_context(agent_id)
            assert latest is not None
            assert len(latest["conversationHistory"]) == len(messages)

    @settings(max_examples=100, deadline=None)
    @given(
        batch1=st.lists(_message, min_size=1, max_size=3),
        batch2=st.lists(_message, min_size=1, max_size=3),
    )
    def test_subsequent_appends_accumulate(
        self, batch1: list[dict], batch2: list[dict]
    ) -> None:
        with mock_aws():
            _create_tables()
            repo = _context_repo()

            agent_id = "agent-context-002"
            repo.append_messages(agent_id, batch1)
            repo.append_messages(agent_id, batch2)

            latest = repo.get_latest_context(agent_id)
            assert latest is not None
            assert len(latest["conversationHistory"]) == len(batch1) + len(batch2)


# ---------------------------------------------------------------------------
# Property 65: Latest state retrieval
# For any agent state query, the latest state should be retrieved from DynamoDB.
# Feature: realtime-agentic-api, Property 65
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestProperty65LatestStateRetrieval:

    @settings(max_examples=100, deadline=None)
    @given(
        user_id=_user_id,
        name=_agent_name,
        config=_agent_config,
        statuses=st.lists(
            st.sampled_from(["idle", "processing", "waiting", "error"]),
            min_size=2,
            max_size=5,
        ),
    )
    def test_get_returns_latest_status(
        self, user_id: str, name: str, config: dict, statuses: list[str]
    ) -> None:
        with mock_aws():
            _create_tables()
            repo = _agent_repo()

            agent = repo.create_agent(user_id=user_id, name=name, configuration=config)
            for s in statuses:
                repo.update_agent_status(agent["agentId"], s)

            retrieved = repo.get_agent(agent["agentId"])
            assert retrieved["status"] == statuses[-1]

    @settings(max_examples=100, deadline=None)
    @given(messages=st.lists(_message, min_size=1, max_size=5))
    def test_latest_context_is_most_recent(self, messages: list[dict]) -> None:
        with mock_aws():
            _create_tables()
            repo = _context_repo()

            agent_id = "agent-latest-001"
            # Write multiple snapshots
            for msg in messages:
                repo.put_context(
                    agent_id=agent_id,
                    conversation_history=[msg],
                )

            latest = repo.get_latest_context(agent_id)
            assert latest is not None
            # Most recent snapshot has the last message
            assert latest["conversationHistory"] == [messages[-1]]


# ---------------------------------------------------------------------------
# Additional data access property tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestAgentDeletion:
    """Property 4: Agent deletion completeness."""

    @settings(max_examples=100, deadline=None)
    @given(user_id=_user_id, name=_agent_name, config=_agent_config)
    def test_deleted_agent_not_found(
        self, user_id: str, name: str, config: dict
    ) -> None:
        with mock_aws():
            _create_tables()
            repo = _agent_repo()

            agent = repo.create_agent(user_id=user_id, name=name, configuration=config)
            repo.delete_agent(agent["agentId"])

            with pytest.raises(ItemNotFoundError):
                repo.get_agent(agent["agentId"])


@pytest.mark.property
class TestConnectionRepository:
    """Tests for WebSocket connection management."""

    @settings(max_examples=100, deadline=None)
    @given(user_id=_user_id)
    def test_connection_lifecycle(self, user_id: str) -> None:
        with mock_aws():
            _create_tables()
            repo = _connection_repo()

            conn = repo.create_connection(connection_id="conn-001", user_id=user_id)
            assert conn["connectionId"] == "conn-001"
            assert conn["userId"] == user_id

            retrieved = repo.get_connection("conn-001")
            assert retrieved["connectionId"] == "conn-001"

            repo.delete_connection("conn-001")
            assert repo.get_connection_or_none("conn-001") is None

    @settings(max_examples=100, deadline=None)
    @given(
        agent_ids=st.lists(
            st.text(min_size=5, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789"),
            min_size=1,
            max_size=5,
            unique=True,
        )
    )
    def test_subscription_management(self, agent_ids: list[str]) -> None:
        with mock_aws():
            _create_tables()
            repo = _connection_repo()

            repo.create_connection(connection_id="conn-sub", user_id="user-1")

            for aid in agent_ids:
                repo.add_subscription("conn-sub", aid)

            subs = repo.get_subscriptions("conn-sub")
            for aid in agent_ids:
                assert aid in subs

            # Remove first subscription
            repo.remove_subscription("conn-sub", agent_ids[0])
            subs_after = repo.get_subscriptions("conn-sub")
            assert agent_ids[0] not in subs_after


@pytest.mark.property
class TestTaskQueryMethods:
    """Tests for task listing and GSI queries."""

    @settings(max_examples=50, deadline=None)
    @given(
        descriptions=st.lists(_task_description, min_size=2, max_size=5, unique=True)
    )
    def test_list_tasks_by_agent(self, descriptions: list[str]) -> None:
        with mock_aws():
            _create_tables()
            repo = _task_repo()

            agent_id = "agent-list-001"
            for desc in descriptions:
                repo.create_task(agent_id=agent_id, description=desc)

            tasks, _ = repo.list_tasks_by_agent(agent_id, limit=50)
            assert len(tasks) == len(descriptions)

    @settings(max_examples=50, deadline=None)
    @given(description=_task_description)
    def test_get_task_by_id_via_gsi(self, description: str) -> None:
        with mock_aws():
            _create_tables()
            repo = _task_repo()

            agent_id = "agent-gsi-001"
            task = repo.create_task(agent_id=agent_id, description=description)

            found = repo.get_task_by_id(task["taskId"])
            assert found["taskId"] == task["taskId"]
            assert found["description"] == description
