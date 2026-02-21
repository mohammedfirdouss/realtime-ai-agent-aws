"""Unit tests for the LLM provider abstraction layer."""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from runtime.shared.llm_provider import (
    AnthropicProvider,
    CircuitBreaker,
    CircuitState,
    LLMAuthenticationError,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMResponseError,
    OpenAIProvider,
    create_llm_provider,
)


class TestLLMRequest:
    def test_valid_request(self):
        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="gpt-4")
        assert req.model == "gpt-4"
        assert req.temperature == 0.7

    def test_empty_messages_raises(self):
        with pytest.raises(ValueError, match="messages must not be empty"):
            LLMRequest(messages=[], model="gpt-4")

    def test_invalid_temperature_raises(self):
        with pytest.raises(ValueError, match="temperature"):
            LLMRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4",
                temperature=3.0,
            )

    def test_invalid_max_tokens_raises(self):
        with pytest.raises(ValueError, match="max_tokens"):
            LLMRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4",
                max_tokens=0,
            )


class TestLLMResponse:
    def test_fields(self):
        resp = LLMResponse(content="hello", model="gpt-4", provider="openai")
        assert resp.content == "hello"
        assert resp.usage == {}


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()

    def test_success_resets_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0.01)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request()


class TestOpenAIProvider:
    def _make_provider(self, **kwargs: Any) -> OpenAIProvider:
        return OpenAIProvider("test-key", max_retries=1, **kwargs)

    def _openai_response(self, content: str = "hello") -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": content}}],
            "model": "gpt-4",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

    @patch("urllib.request.urlopen")
    def test_successful_completion(self, mock_urlopen: MagicMock):
        resp_data = json.dumps(self._openai_response("world")).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        provider = self._make_provider()
        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="gpt-4")
        result = provider.complete(req)

        assert result.content == "world"
        assert result.provider == "openai"
        assert result.usage["total_tokens"] == 15

    @patch("urllib.request.urlopen")
    def test_auth_error_not_retried(self, mock_urlopen: MagicMock):
        import urllib.error

        exc = urllib.error.HTTPError(
            "url", 401, "Unauthorized", {}, MagicMock(read=lambda: b'{}')
        )
        mock_urlopen.side_effect = exc

        provider = OpenAIProvider("test-key", max_retries=3)
        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="gpt-4")
        with pytest.raises(LLMAuthenticationError):
            provider.complete(req)
        assert mock_urlopen.call_count == 1

    @patch("urllib.request.urlopen")
    def test_rate_limit_retried(self, mock_urlopen: MagicMock):
        import urllib.error

        exc = urllib.error.HTTPError(
            "url", 429, "Too Many Requests", {}, MagicMock(read=lambda: b'{}')
        )
        mock_urlopen.side_effect = exc

        provider = OpenAIProvider(
            "test-key", max_retries=2, initial_delay_ms=1, max_delay_ms=1
        )
        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="gpt-4")
        with pytest.raises(LLMProviderError, match="all 2 attempts failed"):
            provider.complete(req)
        assert mock_urlopen.call_count == 2

    def test_build_payload(self):
        req = LLMRequest(
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4",
            temperature=0.5,
            max_tokens=100,
        )
        payload = OpenAIProvider._build_payload(req)
        assert payload["model"] == "gpt-4"
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 100
        assert len(payload["messages"]) == 1

    def test_parse_response_bad_format(self):
        provider = self._make_provider()
        with pytest.raises(LLMResponseError):
            provider._parse_response({"bad": "data"})

    def test_provider_name(self):
        assert self._make_provider().provider_name == "openai"


class TestAnthropicProvider:
    def _make_provider(self, **kwargs: Any) -> AnthropicProvider:
        return AnthropicProvider("test-key", max_retries=1, **kwargs)

    def _anthropic_response(self, content: str = "hello") -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": content}],
            "model": "claude-3-opus-20240229",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

    @patch("urllib.request.urlopen")
    def test_successful_completion(self, mock_urlopen: MagicMock):
        resp_data = json.dumps(self._anthropic_response("hi there")).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        provider = self._make_provider()
        req = LLMRequest(
            messages=[{"role": "user", "content": "hi"}], model="claude-3-opus-20240229"
        )
        result = provider.complete(req)

        assert result.content == "hi there"
        assert result.provider == "anthropic"
        assert result.usage["total_tokens"] == 15

    def test_build_payload_extracts_system(self):
        req = LLMRequest(
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "hello"},
            ],
            model="claude-3-opus-20240229",
        )
        payload = AnthropicProvider._build_payload(req)
        assert payload["system"] == "You are helpful."
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

    def test_build_payload_no_system(self):
        req = LLMRequest(
            messages=[{"role": "user", "content": "hello"}],
            model="claude-3-opus-20240229",
        )
        payload = AnthropicProvider._build_payload(req)
        assert "system" not in payload

    def test_parse_response_bad_format(self):
        provider = self._make_provider()
        with pytest.raises(LLMResponseError):
            provider._parse_response({"bad": "data"})

    def test_provider_name(self):
        assert self._make_provider().provider_name == "anthropic"

    def test_headers_include_api_key_and_version(self):
        provider = self._make_provider()
        headers = provider._build_headers()
        assert headers["x-api-key"] == "test-key"
        assert "anthropic-version" in headers


class TestCreateLLMProvider:
    def test_create_openai_with_key(self):
        provider = create_llm_provider("openai", api_key="sk-test")
        assert isinstance(provider, OpenAIProvider)

    def test_create_anthropic_with_key(self):
        provider = create_llm_provider("anthropic", api_key="sk-ant-test")
        assert isinstance(provider, AnthropicProvider)

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_provider("gemini", api_key="key")

    def test_no_key_source_raises(self):
        with pytest.raises(ValueError, match="Either api_key or secret_name"):
            create_llm_provider("openai")

    @patch("runtime.shared.llm_provider.get_secret", return_value="secret-key")
    def test_create_with_secret_name(self, mock_secret: MagicMock):
        provider = create_llm_provider("openai", secret_name="my/secret")
        assert isinstance(provider, OpenAIProvider)
        mock_secret.assert_called_once_with("my/secret", region=None)


class TestRetryAndCircuitBreaker:
    @patch("urllib.request.urlopen")
    def test_retry_with_backoff(self, mock_urlopen: MagicMock):
        import urllib.error

        success_data = json.dumps({
            "choices": [{"message": {"content": "ok"}}],
            "model": "gpt-4",
            "usage": {},
        }).encode()
        mock_success = MagicMock()
        mock_success.read.return_value = success_data
        mock_success.__enter__ = lambda s: s
        mock_success.__exit__ = MagicMock(return_value=False)

        exc = urllib.error.HTTPError("url", 500, "Server Error", {}, MagicMock(read=lambda: b'{}'))
        mock_urlopen.side_effect = [exc, mock_success]

        provider = OpenAIProvider("key", max_retries=2, initial_delay_ms=1, max_delay_ms=1)
        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="gpt-4")
        result = provider.complete(req)

        assert result.content == "ok"
        assert mock_urlopen.call_count == 2

    def test_circuit_breaker_blocks_request(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()

        provider = OpenAIProvider("key", circuit_breaker=cb)
        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="gpt-4")
        with pytest.raises(LLMProviderError, match="circuit breaker is open"):
            provider.complete(req)
