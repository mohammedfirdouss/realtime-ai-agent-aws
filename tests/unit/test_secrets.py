"""Unit tests for runtime.shared.secrets."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from runtime.shared.secrets import clear_cache, get_secret, get_secret_json


class TestSecrets:
    def setup_method(self) -> None:
        clear_cache()

    def test_get_secret_caches_value(self) -> None:
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": "value"}

        with patch("runtime.shared.secrets.boto3.client", return_value=client) as mock_client:
            assert get_secret("my/secret") == "value"
            assert get_secret("my/secret") == "value"

        mock_client.assert_called_once_with("secretsmanager", region_name=None)
        client.get_secret_value.assert_called_once_with(SecretId="my/secret")

    def test_get_secret_json_parses(self) -> None:
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": json.dumps({"ok": True})}

        with patch("runtime.shared.secrets.boto3.client", return_value=client):
            assert get_secret_json("my/json") == {"ok": True}

    def test_get_secret_raises_client_error(self) -> None:
        client = MagicMock()
        error = ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetSecretValue")
        client.get_secret_value.side_effect = error

        with patch("runtime.shared.secrets.boto3.client", return_value=client):
            with pytest.raises(ClientError):
                get_secret("missing")

    def test_clear_cache_resets_client(self) -> None:
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": "value"}

        with patch("runtime.shared.secrets.boto3.client", return_value=client) as mock_client:
            get_secret("my/secret")
            clear_cache()
            get_secret("my/secret")

        assert mock_client.call_count == 2
