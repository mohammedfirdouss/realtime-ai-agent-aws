"""Cache service with cache-aside pattern for the Realtime Agentic API.

Provides a CacheService class that wraps Redis operations with:
- get/set/delete operations with JSON serialization
- Cache-aside pattern helper methods
 - TTL-based expiration using constants
 - Compatibility with Redis LRU eviction when configured via maxmemory-policy
"""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")
class CacheError(Exception):
    """Raised when a cache operation fails."""
@dataclass(frozen=True)
class CacheConfig:
    """Configuration for the cache service."""

    host: str
    port: int = 6379
    db: int = 0
    socket_timeout: float = 1.0
    socket_connect_timeout: float = 1.0
    decode_responses: bool = True
    max_connections: int = 10
    local_cache_max_size: int = 1000
class LocalLRUCache:
    """Simple in-memory LRU cache for local fallback or testing.

    Used when Redis is not available (e.g., local development, testing)
    or as a first-level cache to reduce Redis round trips.
    """

    def __init__(self, max_size: int = 1000) -> None:
        self._cache: OrderedDict[str, tuple[Any, float | None]] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Any | None:
        """Get a value from the cache. Returns None if not found."""
        if key not in self._cache:
            return None
        if self._is_expired(key):
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return self._cache[key][0]

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in the cache with optional TTL."""
        if key in self._cache:
            self._cache.move_to_end(key)
        expires_at = time.time() + ttl if ttl is not None else None
        self._cache[key] = (value, expires_at)
        # Evict oldest if over capacity
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def delete(self, key: str) -> bool:
        """Delete a key from the cache. Returns True if key existed."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        if key not in self._cache:
            return False
        if self._is_expired(key):
            return False
        return True

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self._cache.clear()

    def size(self) -> int:
        """Return the current number of entries in the cache."""
        return len(self._cache)

    def _is_expired(self, key: str) -> bool:
        value = self._cache.get(key)
        if value is None:
            return True
        expires_at = value[1]
        if expires_at is None:
            return False
        if time.time() >= expires_at:
            self._cache.pop(key, None)
            return True
        return False
@dataclass
class CacheService:
    """Cache service with cache-aside pattern support.

    Provides methods for:
    - Basic get/set/delete operations
    - Cache-aside pattern (get_or_fetch)
    - TTL-based expiration
    - JSON serialization for complex objects

    Uses Redis as the primary cache backend, with a local LRU cache
    as fallback when Redis is unavailable.
    """

    config: CacheConfig | None = None
    local_cache_max_size: int = 1000
    _client: Any = field(default=None, init=False, repr=False)
    _local_cache: LocalLRUCache = field(init=False)
    _use_local_only: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Initialize Redis client if config is provided."""
        # Determine local cache size from config or use provided default
        max_size = self.local_cache_max_size
        if self.config is not None:
            max_size = self.config.local_cache_max_size
        self._local_cache = LocalLRUCache(max_size=max_size)

        if self.config is not None:
            self._connect()
        else:
            self._use_local_only = True
            logger.info("CacheService initialized in local-only mode")

    def _connect(self) -> None:
        """Establish connection to Redis."""
        if self.config is None:
            self._use_local_only = True
            return

        try:
            import redis

            self._client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                decode_responses=self.config.decode_responses,
                max_connections=self.config.max_connections,
            )
            # Test connection
            self._client.ping()
            logger.info("Connected to Redis at %s:%d", self.config.host, self.config.port)
        except ImportError:
            logger.warning("redis-py not installed, falling back to local cache")
            self._use_local_only = True
        except Exception as exc:
            logger.warning("Failed to connect to Redis: %s, falling back to local cache", exc)
            self._use_local_only = True

    # Core Operations

    def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Returns the deserialized value if found, None otherwise.
        Falls back to local cache if Redis is unavailable.
        """
        # Check local cache first
        local_value = self._local_cache.get(key)
        if local_value is not None:
            return local_value

        if self._use_local_only or self._client is None:
            return None

        try:
            raw_value = self._client.get(key)
            if raw_value is None:
                return None
            value = self._deserialize(raw_value)
            # Populate local cache
            self._local_cache.set(key, value)
            return value
        except Exception as exc:
            logger.warning("Cache get failed for key %s: %s", key, exc)
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set a value in the cache with optional TTL in seconds.

        Returns True if the operation was successful.
        """
        serialized = self._serialize(value)

        # Always update local cache
        self._local_cache.set(key, value, ttl)

        if self._use_local_only or self._client is None:
            return True

        try:
            if ttl is not None:
                self._client.setex(key, ttl, serialized)
            else:
                self._client.set(key, serialized)
            return True
        except Exception as exc:
            logger.warning("Cache set failed for key %s: %s", key, exc)
            return False

    def delete(self, key: str) -> bool:
        """Delete a key from the cache.

        Returns True if the key was deleted from either local or Redis cache.
        """
        # Always delete from local cache
        local_deleted = self._local_cache.delete(key)

        if self._use_local_only or self._client is None:
            return local_deleted

        try:
            result = self._client.delete(key)
            return bool(result > 0) or local_deleted
        except Exception as exc:
            logger.warning("Cache delete failed for key %s: %s", key, exc)
            return local_deleted

    def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        if self._local_cache.exists(key):
            return True

        if self._use_local_only or self._client is None:
            return False

        try:
            return bool(self._client.exists(key))
        except Exception as exc:
            logger.warning("Cache exists check failed for key %s: %s", key, exc)
            return False

    # Cache-Aside Pattern

    def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], T | None],
        ttl: int | None = None,
    ) -> T | None:
        """Implement cache-aside pattern.

        1. Check cache for key
        2. If found, return cached value
        3. If not found, call fetch_fn to get value
        4. Store result in cache with optional TTL
        5. Return the value

        Args:
            key: Cache key
            fetch_fn: Function to call if cache miss
            ttl: Time-to-live in seconds (optional)

        Returns:
            The cached or fetched value
        """
        cached_value = self.get(key)
        if cached_value is not None:
            logger.debug("Cache hit for key: %s", key)
            return cast(T, cached_value)

        logger.debug("Cache miss for key: %s, fetching...", key)
        value = fetch_fn()

        if value is not None:
            self.set(key, value, ttl)

        return value

    def invalidate(self, key: str) -> bool:
        """Invalidate a cache entry.

        Alias for delete() to make cache invalidation intent clearer.
        """
        return self.delete(key)

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern.

        Uses Redis SCAN to find matching keys (avoids blocking KEYS command).
        Returns the number of keys deleted.

        Note: In local-only mode, the local cache is cleared and the number
        of cleared entries is returned.
        """
        if self._use_local_only or self._client is None:
            deleted_count = self._local_cache.size()
            self._local_cache.clear()
            return deleted_count

        try:
            deleted_count = 0
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    deleted_count += self._client.delete(*keys)
                    for key in keys:
                        self._local_cache.delete(key)
                if cursor == 0:
                    break
            return deleted_count
        except Exception as exc:
            logger.warning("Cache invalidate_pattern failed for %s: %s", pattern, exc)
            return 0

    # Serialization

    def _serialize(self, value: Any) -> str:
        """Serialize a value to JSON string."""
        return json.dumps(value, default=str)

    def _deserialize(self, raw: str) -> Any:
        """Deserialize a JSON string to a Python object."""
        return json.loads(raw)

    # Health Check

    def health_check(self) -> dict[str, Any]:
        """Check the health of the cache service.

        Returns a dict with status and details.
        """
        result: dict[str, Any] = {
            "local_cache_size": self._local_cache.size(),
            "local_only_mode": self._use_local_only,
        }

        if self._use_local_only or self._client is None:
            result["redis_status"] = "disconnected"
            return result

        try:
            self._client.ping()
            result["redis_status"] = "connected"
            info = self._client.info("memory")
            result["redis_used_memory"] = info.get("used_memory_human", "unknown")
        except Exception as exc:
            result["redis_status"] = f"error: {exc}"

        return result

    # Context Manager

    def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception as exc:
                logger.warning("Failed to close Redis connection: %s", exc)

    def __enter__(self) -> "CacheService":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
def create_cache_service(
    host: str | None = None,
    port: int = 6379,
    **kwargs: Any,
) -> CacheService:
    """Factory function to create a CacheService.

    If host is None, creates a local-only cache service (for testing/development).
    """
    if host is None:
        return CacheService(config=None)

    config = CacheConfig(host=host, port=port, **kwargs)
    return CacheService(config=config)
