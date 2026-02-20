"""Unit tests for the API key authorizer."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any
from unittest.mock import patch

from runtime.auth.api_key_authorizer import (
    _hash_key,
    handler,
    validate_api_key,
)

_METHOD_ARN = "arn:aws:execute-api:us-east-1:123456789012:abc123/dev/GET/agents"


def _make_valid_keys(raw_key: str, user_id: str = "user-1", role: str = "user") -> dict[str, Any]:
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return {key_hash: {"user_id": user_id, "role": role}}


class TestHashKey:
    def test_deterministic(self) -> None:
        assert _hash_key("abc") == _hash_key("abc")

    def test_different_keys_different_hashes(self) -> None:
        assert _hash_key("key1") != _hash_key("key2")

    def test_sha256_format(self) -> None:
        h = _hash_key("test")
        assert len(h) == 64  # 256 bits in hex


class TestValidateApiKey:
    def test_valid_key(self) -> None:
        keys = _make_valid_keys("my-secret-key")
        result = validate_api_key("my-secret-key", keys)
        assert result is not None
        assert result["user_id"] == "user-1"

    def test_invalid_key(self) -> None:
        keys = _make_valid_keys("my-secret-key")
        result = validate_api_key("wrong-key", keys)
        assert result is None

    def test_empty_key(self) -> None:
        keys = _make_valid_keys("my-secret-key")
        result = validate_api_key("", keys)
        assert result is None


class TestApiKeyAuthorizerHandler:
    def _token_event(self, api_key: str) -> dict[str, Any]:
        return {
            "type": "TOKEN",
            "authorizationToken": api_key,
            "methodArn": _METHOD_ARN,
        }

    def _request_event(self, api_key: str) -> dict[str, Any]:
        return {
            "type": "REQUEST",
            "headers": {"x-api-key": api_key},
            "methodArn": _METHOD_ARN,
        }

    @patch.dict(os.environ, {"API_KEYS_SECRET_NAME": "test/api-keys"})
    @patch("runtime.auth.api_key_authorizer.get_secret")
    def test_valid_token_authorizer(self, mock_get_secret: Any) -> None:
        raw_key = "my-api-key-123"
        mock_get_secret.return_value = json.dumps(_make_valid_keys(raw_key, "user-42", "admin"))

        result = handler(self._token_event(raw_key), None)

        assert result["principalId"] == "user-42"
        stmt = result["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Allow"
        assert result["context"]["role"] == "admin"
        assert result["context"]["auth_type"] == "api_key"

    @patch.dict(os.environ, {"API_KEYS_SECRET_NAME": "test/api-keys"})
    @patch("runtime.auth.api_key_authorizer.get_secret")
    def test_valid_request_authorizer(self, mock_get_secret: Any) -> None:
        raw_key = "my-api-key-123"
        mock_get_secret.return_value = json.dumps(_make_valid_keys(raw_key))

        result = handler(self._request_event(raw_key), None)

        assert result["principalId"] == "user-1"
        stmt = result["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Allow"

    @patch.dict(os.environ, {"API_KEYS_SECRET_NAME": "test/api-keys"})
    @patch("runtime.auth.api_key_authorizer.get_secret")
    def test_invalid_key_denied(self, mock_get_secret: Any) -> None:
        mock_get_secret.return_value = json.dumps(_make_valid_keys("correct-key"))

        result = handler(self._token_event("wrong-key"), None)

        assert result["principalId"] == "anonymous"
        stmt = result["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Deny"

    @patch.dict(os.environ, {"API_KEYS_SECRET_NAME": "test/api-keys"})
    def test_missing_token_denied(self) -> None:
        event = {"methodArn": _METHOD_ARN}
        result = handler(event, None)

        assert result["principalId"] == "anonymous"
        stmt = result["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Deny"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_env_var_denied(self) -> None:
        # Clear ALL env vars to ensure API_KEYS_SECRET_NAME is missing
        event = self._token_event("some-key")
        result = handler(event, None)

        assert result["principalId"] == "anonymous"
        stmt = result["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Deny"
