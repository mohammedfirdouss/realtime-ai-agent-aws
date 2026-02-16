"""Unit tests for shared constants."""

from runtime.shared.constants import (
    VALID_AGENT_STATUSES,
    VALID_LLM_PROVIDERS,
    VALID_TASK_STATUSES,
)


class TestConstants:
    def test_agent_statuses_not_empty(self) -> None:
        assert len(VALID_AGENT_STATUSES) == 4

    def test_task_statuses_not_empty(self) -> None:
        assert len(VALID_TASK_STATUSES) == 5

    def test_llm_providers(self) -> None:
        assert "openai" in VALID_LLM_PROVIDERS
        assert "anthropic" in VALID_LLM_PROVIDERS

    def test_statuses_are_frozensets(self) -> None:
        assert isinstance(VALID_AGENT_STATUSES, frozenset)
        assert isinstance(VALID_TASK_STATUSES, frozenset)
        assert isinstance(VALID_LLM_PROVIDERS, frozenset)
