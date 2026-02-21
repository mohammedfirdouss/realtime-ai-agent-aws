"""LLM provider abstraction layer.

Defines the base ``LLMProvider`` interface and concrete implementations
for OpenAI and Anthropic.  Provider instances are created via
``create_llm_provider`` which resolves API keys from Secrets Manager.
"""

from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from runtime.shared.constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF_MULTIPLIER,
    DEFAULT_RETRY_INITIAL_DELAY_MS,
    DEFAULT_RETRY_MAX_DELAY_MS,
    LLM_PROVIDER_ANTHROPIC,
    LLM_PROVIDER_OPENAI,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    VALID_LLM_PROVIDERS,
)
from runtime.shared.secrets import get_secret

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""


class LLMRateLimitError(LLMProviderError):
    """Raised when the provider returns a rate-limit response."""


class LLMAuthenticationError(LLMProviderError):
    """Raised when API authentication fails (non-retryable)."""


class LLMResponseError(LLMProviderError):
    """Raised when the provider returns an unexpected response."""


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Simple circuit breaker to avoid hammering a failing provider."""

    failure_threshold: int = 5
    recovery_timeout_seconds: float = 60.0
    _failure_count: int = field(default=0, init=False, repr=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False, repr=False)
    _last_failure_time: float = field(default=0.0, init=False, repr=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker opened after %d failures", self._failure_count
            )

    def allow_request(self) -> bool:
        current = self.state
        return current in (CircuitState.CLOSED, CircuitState.HALF_OPEN)


@dataclass(frozen=True)
class LLMRequest:
    """Normalised request for an LLM completion."""

    messages: list[dict[str, str]]
    model: str
    temperature: float = 0.7
    max_tokens: int = 1024
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("messages must not be empty")
        if not (TEMPERATURE_MIN <= self.temperature <= TEMPERATURE_MAX):
            raise ValueError(
                f"temperature must be between {TEMPERATURE_MIN} and {TEMPERATURE_MAX}"
            )
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")


@dataclass(frozen=True)
class LLMResponse:
    """Normalised response from an LLM completion."""

    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(abc.ABC):
    """Abstract base class for LLM provider integrations."""

    def __init__(
        self,
        api_key: str,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay_ms: int = DEFAULT_RETRY_INITIAL_DELAY_MS,
        max_delay_ms: int = DEFAULT_RETRY_MAX_DELAY_MS,
        backoff_multiplier: float = DEFAULT_RETRY_BACKOFF_MULTIPLIER,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_retries = max_retries
        self._initial_delay_ms = initial_delay_ms
        self._max_delay_ms = max_delay_ms
        self._backoff_multiplier = backoff_multiplier
        self._circuit_breaker = circuit_breaker or CircuitBreaker()

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier (e.g. ``openai``)."""

    @abc.abstractmethod
    def _call_api(self, request: LLMRequest) -> LLMResponse:
        """Provider-specific API call.  Implementations should raise
        ``LLMRateLimitError`` for 429s and ``LLMProviderError`` for other
        transient failures.
        """

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send *request* to the provider with retry + circuit-breaker."""
        if not self._circuit_breaker.allow_request():
            raise LLMProviderError(
                f"{self.provider_name} circuit breaker is open – request blocked"
            )

        last_error: Exception | None = None
        delay_ms = self._initial_delay_ms

        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._call_api(request)
                self._circuit_breaker.record_success()
                return response
            except LLMAuthenticationError:
                self._circuit_breaker.record_failure()
                raise
            except LLMProviderError as exc:
                last_error = exc
                self._circuit_breaker.record_failure()
                if attempt < self._max_retries:
                    sleep_s = min(delay_ms, self._max_delay_ms) / 1000.0
                    logger.warning(
                        "%s attempt %d/%d failed: %s – retrying in %.2fs",
                        self.provider_name,
                        attempt,
                        self._max_retries,
                        exc,
                        sleep_s,
                    )
                    time.sleep(sleep_s)
                    delay_ms = int(delay_ms * self._backoff_multiplier)

        raise LLMProviderError(
            f"{self.provider_name}: all {self._max_retries} attempts failed"
        ) from last_error


class OpenAIProvider(LLMProvider):
    """OpenAI chat-completion provider (``/v1/chat/completions``)."""

    _DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, **kwargs)
        self._base_url = base_url or self._DEFAULT_BASE_URL

    @property
    def provider_name(self) -> str:
        return LLM_PROVIDER_OPENAI

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _call_api(self, request: LLMRequest) -> LLMResponse:
        import urllib.error
        import urllib.request

        url = f"{self._base_url}/chat/completions"
        payload = self._build_payload(request)
        headers = self._build_headers()

        import json

        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                err_body = json.loads(exc.read().decode())
            except Exception:
                err_body = {}
            if status == 401:
                raise LLMAuthenticationError("OpenAI: invalid API key") from exc
            if status == 429:
                raise LLMRateLimitError("OpenAI: rate limited") from exc
            raise LLMProviderError(
                f"OpenAI API error {status}: {err_body}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMProviderError(f"OpenAI connection error: {exc}") from exc

        return self._parse_response(body)

    @staticmethod
    def _build_payload(request: LLMRequest) -> dict[str, Any]:
        return {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

    def _parse_response(self, body: dict[str, Any]) -> LLMResponse:
        try:
            choice = body["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMResponseError(f"OpenAI: unexpected response format: {body}") from exc

        usage = body.get("usage", {})
        return LLMResponse(
            content=content,
            model=body.get("model", ""),
            provider=self.provider_name,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            raw=body,
        )


class AnthropicProvider(LLMProvider):
    """Anthropic messages API provider (``/v1/messages``)."""

    _DEFAULT_BASE_URL = "https://api.anthropic.com"
    _API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, **kwargs)
        self._base_url = base_url or self._DEFAULT_BASE_URL

    @property
    def provider_name(self) -> str:
        return LLM_PROVIDER_ANTHROPIC

    def _build_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": self._API_VERSION,
            "Content-Type": "application/json",
        }

    def _call_api(self, request: LLMRequest) -> LLMResponse:
        import urllib.error
        import urllib.request

        url = f"{self._base_url}/v1/messages"
        payload = self._build_payload(request)
        headers = self._build_headers()

        import json

        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                err_body = json.loads(exc.read().decode())
            except Exception:
                err_body = {}
            if status == 401:
                raise LLMAuthenticationError("Anthropic: invalid API key") from exc
            if status == 429:
                raise LLMRateLimitError("Anthropic: rate limited") from exc
            raise LLMProviderError(
                f"Anthropic API error {status}: {err_body}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMProviderError(f"Anthropic connection error: {exc}") from exc

        return self._parse_response(body)

    @staticmethod
    def _build_payload(request: LLMRequest) -> dict[str, Any]:
        system_msg = None
        messages = []
        for msg in request.messages:
            if msg.get("role") == "system":
                system_msg = msg.get("content", "")
            else:
                messages.append({"role": msg["role"], "content": msg["content"]})

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if system_msg:
            payload["system"] = system_msg
        return payload

    def _parse_response(self, body: dict[str, Any]) -> LLMResponse:
        try:
            content_blocks = body["content"]
            content = "".join(
                block["text"] for block in content_blocks if block.get("type") == "text"
            )
        except (KeyError, IndexError) as exc:
            raise LLMResponseError(
                f"Anthropic: unexpected response format: {body}"
            ) from exc

        usage = body.get("usage", {})
        return LLMResponse(
            content=content,
            model=body.get("model", ""),
            provider=self.provider_name,
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": (
                    usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                ),
            },
            raw=body,
        )


def create_llm_provider(
    provider_name: str,
    *,
    api_key: str | None = None,
    secret_name: str | None = None,
    region: str | None = None,
    **kwargs: Any,
) -> LLMProvider:
    """Factory that creates the appropriate ``LLMProvider``.

    Supply *api_key* directly or *secret_name* to load from Secrets Manager.

    Args:
        provider_name: ``"openai"`` or ``"anthropic"``.
        api_key: Explicit API key.
        secret_name: Secrets Manager secret name/ARN for the API key.
        region: AWS region for Secrets Manager lookup.
        **kwargs: Forwarded to the provider constructor.

    Returns:
        An initialised ``LLMProvider`` instance.

    Raises:
        ValueError: If *provider_name* is not recognised or no key source given.
    """
    if provider_name not in VALID_LLM_PROVIDERS:
        raise ValueError(
            f"Unknown LLM provider '{provider_name}'. Must be one of: {sorted(VALID_LLM_PROVIDERS)}"
        )

    if api_key is None and secret_name is None:
        raise ValueError("Either api_key or secret_name must be provided")

    resolved_key = api_key or get_secret(secret_name, region=region)  # type: ignore[arg-type]

    if provider_name == LLM_PROVIDER_OPENAI:
        return OpenAIProvider(resolved_key, **kwargs)
    return AnthropicProvider(resolved_key, **kwargs)
