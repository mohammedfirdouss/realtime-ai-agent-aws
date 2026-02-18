"""Unit tests for the JWT authorizer."""

from __future__ import annotations

import os
import time
from typing import Any
from unittest.mock import patch

from runtime.auth.jwt_authorizer import (
    create_jwt,
    decode_jwt,
    extract_user_identity,
    handler,
)

_METHOD_ARN = "arn:aws:execute-api:us-east-1:123456789012:abc123/dev/GET/agents"
_SIGNING_KEY = "test-secret-key-for-unit-tests"


class TestDecodeJwt:
    def test_valid_token(self) -> None:
        payload = {"sub": "user-1", "role": "admin", "exp": time.time() + 3600}
        token = create_jwt(payload, _SIGNING_KEY)
        claims = decode_jwt(token, _SIGNING_KEY)
        assert claims is not None
        assert claims["sub"] == "user-1"
        assert claims["role"] == "admin"

    def test_expired_token(self) -> None:
        payload = {"sub": "user-1", "exp": time.time() - 100}
        token = create_jwt(payload, _SIGNING_KEY)
        claims = decode_jwt(token, _SIGNING_KEY)
        assert claims is None

    def test_wrong_key_rejected(self) -> None:
        payload = {"sub": "user-1", "exp": time.time() + 3600}
        token = create_jwt(payload, _SIGNING_KEY)
        claims = decode_jwt(token, "wrong-key")
        assert claims is None

    def test_malformed_token_rejected(self) -> None:
        assert decode_jwt("not.a.valid-token", _SIGNING_KEY) is None

    def test_missing_parts_rejected(self) -> None:
        assert decode_jwt("onlyone", _SIGNING_KEY) is None

    def test_no_exp_claim_accepted(self) -> None:
        payload = {"sub": "user-1", "role": "user"}
        token = create_jwt(payload, _SIGNING_KEY)
        claims = decode_jwt(token, _SIGNING_KEY)
        assert claims is not None
        assert claims["sub"] == "user-1"

    def test_tampered_payload_rejected(self) -> None:
        payload = {"sub": "user-1", "role": "admin"}
        token = create_jwt(payload, _SIGNING_KEY)
        parts = token.split(".")
        # Tamper with payload
        import base64

        tampered = base64.urlsafe_b64encode(b'{"sub":"hacker","role":"admin"}').rstrip(b"=")
        parts[1] = tampered.decode()
        tampered_token = ".".join(parts)
        assert decode_jwt(tampered_token, _SIGNING_KEY) is None


class TestCreateJwt:
    def test_roundtrip(self) -> None:
        payload = {"sub": "user-1", "iss": "test", "exp": time.time() + 3600}
        token = create_jwt(payload, _SIGNING_KEY)
        claims = decode_jwt(token, _SIGNING_KEY)
        assert claims is not None
        assert claims["sub"] == "user-1"
        assert claims["iss"] == "test"

    def test_token_format(self) -> None:
        token = create_jwt({"sub": "x"}, _SIGNING_KEY)
        parts = token.split(".")
        assert len(parts) == 3


class TestExtractUserIdentity:
    def test_extracts_sub_and_role(self) -> None:
        claims = {"sub": "user-99", "role": "admin"}
        identity = extract_user_identity(claims)
        assert identity["user_id"] == "user-99"
        assert identity["role"] == "admin"

    def test_defaults_for_missing_fields(self) -> None:
        identity = extract_user_identity({})
        assert identity["user_id"] == "unknown"
        assert identity["role"] == "user"

    def test_invalid_role_falls_back_to_user(self) -> None:
        claims = {"sub": "user-1", "role": "superadmin"}
        identity = extract_user_identity(claims)
        assert identity["role"] == "user"


class TestJwtAuthorizerHandler:
    def _token_event(self, token: str) -> dict[str, Any]:
        return {
            "type": "TOKEN",
            "authorizationToken": f"Bearer {token}",
            "methodArn": _METHOD_ARN,
        }

    def _request_event(self, token: str) -> dict[str, Any]:
        return {
            "type": "REQUEST",
            "headers": {"Authorization": f"Bearer {token}"},
            "methodArn": _METHOD_ARN,
        }

    @patch.dict(os.environ, {"JWT_SECRET_NAME": "test/jwt-secret"})
    @patch("runtime.auth.jwt_authorizer.get_secret")
    def test_valid_token_allowed(self, mock_get_secret: Any) -> None:
        mock_get_secret.return_value = _SIGNING_KEY
        payload = {"sub": "user-1", "role": "user", "exp": time.time() + 3600}
        token = create_jwt(payload, _SIGNING_KEY)

        result = handler(self._token_event(token), None)

        assert result["principalId"] == "user-1"
        stmt = result["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Allow"
        assert result["context"]["auth_type"] == "jwt"

    @patch.dict(os.environ, {"JWT_SECRET_NAME": "test/jwt-secret"})
    @patch("runtime.auth.jwt_authorizer.get_secret")
    def test_request_authorizer(self, mock_get_secret: Any) -> None:
        mock_get_secret.return_value = _SIGNING_KEY
        payload = {"sub": "user-2", "role": "admin", "exp": time.time() + 3600}
        token = create_jwt(payload, _SIGNING_KEY)

        result = handler(self._request_event(token), None)

        assert result["principalId"] == "user-2"
        stmt = result["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Allow"

    @patch.dict(os.environ, {"JWT_SECRET_NAME": "test/jwt-secret"})
    @patch("runtime.auth.jwt_authorizer.get_secret")
    def test_expired_token_denied(self, mock_get_secret: Any) -> None:
        mock_get_secret.return_value = _SIGNING_KEY
        payload = {"sub": "user-1", "exp": time.time() - 100}
        token = create_jwt(payload, _SIGNING_KEY)

        result = handler(self._token_event(token), None)

        assert result["principalId"] == "anonymous"
        stmt = result["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Deny"

    @patch.dict(os.environ, {"JWT_SECRET_NAME": "test/jwt-secret"})
    def test_missing_bearer_token_denied(self) -> None:
        event = {"methodArn": _METHOD_ARN}
        result = handler(event, None)

        assert result["principalId"] == "anonymous"
        stmt = result["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Deny"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_env_var_denied(self) -> None:
        event = self._token_event("some-token")
        result = handler(event, None)

        assert result["principalId"] == "anonymous"
        stmt = result["policyDocument"]["Statement"][0]
        assert stmt["Effect"] == "Deny"
