"""Unit tests for the CacheService class."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from runtime.shared.cache_service import (
    CacheConfig,
    CacheService,
    LocalLRUCache,
    create_cache_service,
)


class TestLocalLRUCache:
    """Tests for the LocalLRUCache class."""

    def test_get_nonexistent_key_returns_none(self) -> None:
        cache = LocalLRUCache()
        assert cache.get("nonexistent") is None

    def test_set_and_get(self) -> None:
        cache = LocalLRUCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_set_with_ttl(self) -> None:
        cache = LocalLRUCache()
        cache.set("key1", "value1", ttl=300)
        assert cache.get("key1") == "value1"

    def test_ttl_expired_evicted(self) -> None:
        cache = LocalLRUCache()
        with patch("runtime.shared.cache_service.time.time") as mock_time:
            mock_time.return_value = 1000.0
            cache.set("key1", "value1", ttl=10)
            assert cache.get("key1") == "value1"
            mock_time.return_value = 1011.0
            assert cache.get("key1") is None
            assert cache.exists("key1") is False

    def test_delete_existing_key(self) -> None:
        cache = LocalLRUCache()
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None

    def test_delete_nonexistent_key(self) -> None:
        cache = LocalLRUCache()
        assert cache.delete("nonexistent") is False

    def test_exists_true(self) -> None:
        cache = LocalLRUCache()
        cache.set("key1", "value1")
        assert cache.exists("key1") is True

    def test_exists_false(self) -> None:
        cache = LocalLRUCache()
        assert cache.exists("nonexistent") is False

    def test_clear(self) -> None:
        cache = LocalLRUCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.size() == 0

    def test_size(self) -> None:
        cache = LocalLRUCache()
        assert cache.size() == 0
        cache.set("key1", "value1")
        assert cache.size() == 1
        cache.set("key2", "value2")
        assert cache.size() == 2

    def test_lru_eviction(self) -> None:
        cache = LocalLRUCache(max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        # Access key1 to make it recently used
        cache.get("key1")
        # Add key4, should evict key2 (oldest)
        cache.set("key4", "value4")
        assert cache.get("key2") is None
        assert cache.get("key1") == "value1"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_update_moves_to_end(self) -> None:
        cache = LocalLRUCache(max_size=2)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        # Update key1, making it recently used
        cache.set("key1", "new_value1")
        # Add key3, should evict key2 (now oldest)
        cache.set("key3", "value3")
        assert cache.get("key2") is None
        assert cache.get("key1") == "new_value1"
        assert cache.get("key3") == "value3"
class TestCacheServiceLocalOnly:
    """Tests for CacheService in local-only mode (no Redis)."""

    def test_local_only_mode_when_no_config(self) -> None:
        service = CacheService(config=None)
        assert service._use_local_only is True

    def test_set_and_get_local_only(self) -> None:
        service = CacheService(config=None)
        service.set("key1", {"data": "value1"})
        assert service.get("key1") == {"data": "value1"}

    def test_set_with_ttl_local_only(self) -> None:
        service = CacheService(config=None)
        service.set("key1", "value1", ttl=300)
        assert service.get("key1") == "value1"

    def test_delete_local_only(self) -> None:
        service = CacheService(config=None)
        service.set("key1", "value1")
        assert service.delete("key1") is True
        assert service.get("key1") is None

    def test_delete_nonexistent_key_local_only(self) -> None:
        service = CacheService(config=None)
        assert service.delete("nonexistent") is False

    def test_exists_local_only(self) -> None:
        service = CacheService(config=None)
        service.set("key1", "value1")
        assert service.exists("key1") is True
        assert service.exists("nonexistent") is False

    def test_health_check_local_only(self) -> None:
        service = CacheService(config=None)
        health = service.health_check()
        assert health["local_only_mode"] is True
        assert health["redis_status"] == "disconnected"
        assert "local_cache_size" in health

    def test_invalidate_pattern_local_only(self) -> None:
        service = CacheService(config=None)
        service.set("agent:1", "value1")
        service.set("agent:2", "value2")
        deleted = service.invalidate_pattern("agent:*")
        assert deleted == 2
        assert service.get("agent:1") is None
class TestCacheServiceCacheAside:
    """Tests for cache-aside pattern implementation."""

    def test_get_or_fetch_cache_miss(self) -> None:
        service = CacheService(config=None)
        fetch_count = 0

        def fetch_fn() -> str:
            nonlocal fetch_count
            fetch_count += 1
            return "fetched_value"

        result = service.get_or_fetch("key1", fetch_fn)
        assert result == "fetched_value"
        assert fetch_count == 1
        # Value should now be cached
        assert service.get("key1") == "fetched_value"

    def test_get_or_fetch_cache_hit(self) -> None:
        service = CacheService(config=None)
        service.set("key1", "cached_value")
        fetch_count = 0

        def fetch_fn() -> str:
            nonlocal fetch_count
            fetch_count += 1
            return "fetched_value"

        result = service.get_or_fetch("key1", fetch_fn)
        assert result == "cached_value"
        assert fetch_count == 0  # fetch_fn should not be called

    def test_get_or_fetch_with_ttl(self) -> None:
        service = CacheService(config=None)

        def fetch_fn() -> dict[str, Any]:
            return {"data": "value"}

        result = service.get_or_fetch("key1", fetch_fn, ttl=300)
        assert result == {"data": "value"}

    def test_invalidate(self) -> None:
        service = CacheService(config=None)
        service.set("key1", "value1")
        assert service.invalidate("key1") is True
        assert service.get("key1") is None
class TestCacheServiceSerialization:
    """Tests for JSON serialization/deserialization."""

    def test_serialize_dict(self) -> None:
        service = CacheService(config=None)
        data = {"name": "test", "count": 42, "active": True}
        service.set("key1", data)
        assert service.get("key1") == data

    def test_serialize_list(self) -> None:
        service = CacheService(config=None)
        data = [1, 2, 3, "four", {"five": 5}]
        service.set("key1", data)
        assert service.get("key1") == data

    def test_serialize_nested(self) -> None:
        service = CacheService(config=None)
        data = {
            "level1": {
                "level2": {
                    "level3": [1, 2, 3],
                },
            },
        }
        service.set("key1", data)
        assert service.get("key1") == data
class TestCacheServiceWithMockedRedis:
    """Tests for CacheService with mocked Redis client."""

    def test_connect_success(self) -> None:
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_redis_module.Redis.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            config = CacheConfig(host="localhost", port=6379)
            service = CacheService(config=config)

            assert service._use_local_only is False
            mock_client.ping.assert_called_once()

    def test_get_from_redis(self) -> None:
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.get.return_value = '{"data": "value"}'
        mock_redis_module.Redis.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            config = CacheConfig(host="localhost", port=6379)
            service = CacheService(config=config)
            result = service.get("key1")

            assert result == {"data": "value"}
            mock_client.get.assert_called_once_with("key1")

    def test_set_to_redis_with_ttl(self) -> None:
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_redis_module.Redis.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            config = CacheConfig(host="localhost", port=6379)
            service = CacheService(config=config)
            service.set("key1", {"data": "value"}, ttl=300)

            mock_client.setex.assert_called_once()
            call_args = mock_client.setex.call_args
            assert call_args[0][0] == "key1"
            assert call_args[0][1] == 300

    def test_set_to_redis_without_ttl(self) -> None:
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_redis_module.Redis.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            config = CacheConfig(host="localhost", port=6379)
            service = CacheService(config=config)
            service.set("key1", "value1")

            mock_client.set.assert_called_once()

    def test_invalidate_pattern_uses_scan(self) -> None:
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.scan.side_effect = [(1, ["a", "b"]), (0, ["c"])]
        mock_client.delete.side_effect = [2, 1]
        mock_redis_module.Redis.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            config = CacheConfig(host="localhost", port=6379)
            service = CacheService(config=config)
            service._local_cache.set("a", 1)
            service._local_cache.set("b", 2)
            service._local_cache.set("c", 3)

            deleted = service.invalidate_pattern("a*")

        assert deleted == 3
        assert service._local_cache.size() == 0

    def test_delete_from_redis(self) -> None:
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.delete.return_value = 1
        mock_redis_module.Redis.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            config = CacheConfig(host="localhost", port=6379)
            service = CacheService(config=config)
            result = service.delete("key1")

            assert result is True
            mock_client.delete.assert_called_once_with("key1")
class TestCreateCacheService:
    """Tests for the create_cache_service factory function."""

    def test_create_local_only(self) -> None:
        service = create_cache_service()
        assert service._use_local_only is True

    def test_create_with_host(self) -> None:
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_redis_module.Redis.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            service = create_cache_service(host="localhost", port=6379)
            assert service.config is not None
            assert service.config.host == "localhost"
            assert service.config.port == 6379
class TestCacheServiceContextManager:
    """Tests for context manager functionality."""

    def test_context_manager_enter_exit(self) -> None:
        with CacheService(config=None) as service:
            service.set("key1", "value1")
            assert service.get("key1") == "value1"

    def test_close_calls_redis_close(self) -> None:
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_redis_module.Redis.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            config = CacheConfig(host="localhost", port=6379)
            service = CacheService(config=config)
            service.close()

            mock_client.close.assert_called_once()
