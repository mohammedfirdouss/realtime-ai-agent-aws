"""Shared constants used across Lambda functions."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Event sources and detail types (EventBridge)
# ---------------------------------------------------------------------------
EVENT_SOURCE_AGENTS = "realtime-agentic-api.agents"
EVENT_SOURCE_TASKS = "realtime-agentic-api.tasks"
EVENT_SOURCE_STATUS = "realtime-agentic-api.status"
EVENT_SOURCE_ERRORS = "realtime-agentic-api.errors"
EVENT_SOURCE_SCHEDULER = "realtime-agentic-api.scheduler"

EVENT_AGENT_CREATED = "AgentCreated"
EVENT_AGENT_DELETED = "AgentDeleted"
EVENT_TASK_CREATED = "TaskCreated"
EVENT_TASK_COMPLETED = "TaskCompleted"
EVENT_TASK_PROGRESS = "TaskProgress"
EVENT_STATUS_CHANGED = "AgentStatusChanged"
EVENT_ERROR_OCCURRED = "ErrorOccurred"
EVENT_SCHEDULED_TASK = "ScheduledTask"

# ---------------------------------------------------------------------------
# Agent statuses
# ---------------------------------------------------------------------------
AGENT_STATUS_IDLE = "idle"
AGENT_STATUS_PROCESSING = "processing"
AGENT_STATUS_WAITING = "waiting"
AGENT_STATUS_ERROR = "error"

VALID_AGENT_STATUSES = frozenset(
    {AGENT_STATUS_IDLE, AGENT_STATUS_PROCESSING, AGENT_STATUS_WAITING, AGENT_STATUS_ERROR}
)

# ---------------------------------------------------------------------------
# Task statuses
# ---------------------------------------------------------------------------
TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_CANCELLED = "cancelled"

VALID_TASK_STATUSES = frozenset(
    {
        TASK_STATUS_PENDING,
        TASK_STATUS_RUNNING,
        TASK_STATUS_COMPLETED,
        TASK_STATUS_FAILED,
        TASK_STATUS_CANCELLED,
    }
)

# ---------------------------------------------------------------------------
# Step statuses
# ---------------------------------------------------------------------------
STEP_STATUS_PENDING = "pending"
STEP_STATUS_RUNNING = "running"
STEP_STATUS_COMPLETED = "completed"
STEP_STATUS_FAILED = "failed"
STEP_STATUS_SKIPPED = "skipped"

# ---------------------------------------------------------------------------
# Step types
# ---------------------------------------------------------------------------
STEP_TYPE_REASONING = "reasoning"
STEP_TYPE_TOOL_CALL = "tool_call"
STEP_TYPE_RESPONSE = "response"
STEP_TYPE_DECISION = "decision"

# ---------------------------------------------------------------------------
# LLM Providers
# ---------------------------------------------------------------------------
LLM_PROVIDER_OPENAI = "openai"
LLM_PROVIDER_ANTHROPIC = "anthropic"

VALID_LLM_PROVIDERS = frozenset({LLM_PROVIDER_OPENAI, LLM_PROVIDER_ANTHROPIC})

# ---------------------------------------------------------------------------
# DynamoDB key prefixes
# ---------------------------------------------------------------------------
PK_AGENT = "AGENT#"
PK_TASK = "TASK#"
PK_CONTEXT = "CONTEXT#"
PK_CONNECTION = "CONNECTION#"
PK_USER = "USER#"

SK_METADATA = "METADATA"

# ---------------------------------------------------------------------------
# Retry / resilience
# ---------------------------------------------------------------------------
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_INITIAL_DELAY_MS = 100
DEFAULT_RETRY_MAX_DELAY_MS = 10_000
DEFAULT_RETRY_BACKOFF_MULTIPLIER = 2.0

RETRYABLE_ERROR_CODES = frozenset(
    {
        "ThrottlingException",
        "ServiceUnavailable",
        "InternalServerError",
        "TimeoutError",
    }
)

# ---------------------------------------------------------------------------
# Cache TTLs (seconds)
# ---------------------------------------------------------------------------
CACHE_TTL_AGENT_CONFIG = 300  # 5 minutes
CACHE_TTL_TASK_STATUS = 30  # 30 seconds
CACHE_TTL_AUTH_TOKEN = 3600  # 1 hour
CACHE_TTL_LLM_RESPONSE = 3600  # 1 hour

# ---------------------------------------------------------------------------
# Validation limits
# ---------------------------------------------------------------------------
MAX_TASK_DESCRIPTION_LENGTH = 10_000
MAX_SYSTEM_PROMPT_LENGTH = 10_000
MAX_TOOLS_PER_AGENT = 50
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0
