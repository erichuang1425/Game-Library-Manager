"""
Cache utilities for Game Library Manager.

Provides bounded LRU caches to prevent unbounded memory growth.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Generic, Optional, Tuple, TypeVar
import time
import threading

from app.logging_utils import get_logger, kv

_log = get_logger("cache_utils")

K = TypeVar("K")
V = TypeVar("V")


class BoundedCache(Generic[K, V]):
    """
    LRU cache with maximum size and optional TTL.

    Thread-safe implementation using OrderedDict for O(1) operations.

    Usage:
        cache = BoundedCache[str, str](max_size=100, ttl_seconds=3600)
        cache.set("key", "value")
        value = cache.get("key")  # Returns "value" or None if expired/missing
    """

    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: Optional[float] = None,
        name: str = "cache",
    ) -> None:
        """
        Initialize bounded cache.

        Args:
            max_size: Maximum number of entries (default: 100)
            ttl_seconds: Optional time-to-live in seconds
            name: Name for logging purposes
        """
        self._cache: OrderedDict[K, Tuple[V, float]] = OrderedDict()
        self._max_size = max(1, max_size)
        self._ttl = ttl_seconds
        self._name = name
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """
        Get value from cache.

        Moves key to end (most recently used) if found and not expired.

        Args:
            key: Cache key
            default: Default value if key not found or expired

        Returns:
            Cached value or default
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return default

            value, timestamp = self._cache[key]

            # Check TTL
            if self._ttl is not None:
                if time.time() - timestamp > self._ttl:
                    del self._cache[key]
                    self._misses += 1
                    return default

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: K, value: V) -> None:
        """
        Set value in cache.

        Evicts oldest entry if at capacity.

        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            if key in self._cache:
                # Update existing
                self._cache.move_to_end(key)
            else:
                # Evict oldest if at capacity
                while len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)

            self._cache[key] = (value, time.time())

    def invalidate(self, key: K) -> bool:
        """
        Remove a specific key from cache.

        Args:
            key: Key to remove

        Returns:
            True if key was present
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> int:
        """
        Clear all entries from cache.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def contains(self, key: K) -> bool:
        """Check if key is in cache (without updating LRU order)."""
        with self._lock:
            if key not in self._cache:
                return False
            if self._ttl is not None:
                _, timestamp = self._cache[key]
                if time.time() - timestamp > self._ttl:
                    return False
            return True

    def prune_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        if self._ttl is None:
            return 0

        with self._lock:
            now = time.time()
            expired = [
                k for k, (_, ts) in self._cache.items()
                if now - ts > self._ttl
            ]
            for k in expired:
                del self._cache[k]
            return len(expired)

    @property
    def size(self) -> int:
        """Current number of entries in cache."""
        with self._lock:
            return len(self._cache)

    @property
    def max_size(self) -> int:
        """Maximum cache size."""
        return self._max_size

    @property
    def stats(self) -> Dict[str, Any]:
        """Cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "name": self._name,
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 3),
                "ttl_seconds": self._ttl,
            }

    def __len__(self) -> int:
        return self.size

    def __contains__(self, key: K) -> bool:
        return self.contains(key)


class TimestampedCache(BoundedCache[K, V]):
    """
    BoundedCache variant that also stores and returns timestamps.

    Useful when caller needs to know when a value was cached.
    """

    def get_with_timestamp(
        self,
        key: K
    ) -> Optional[Tuple[V, float]]:
        """
        Get value and its timestamp from cache.

        Args:
            key: Cache key

        Returns:
            Tuple of (value, timestamp) or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, timestamp = self._cache[key]

            # Check TTL
            if self._ttl is not None:
                if time.time() - timestamp > self._ttl:
                    del self._cache[key]
                    self._misses += 1
                    return None

            self._cache.move_to_end(key)
            self._hits += 1
            return (value, timestamp)


def cached(
    cache: BoundedCache,
    key_func: Optional[Callable[..., Any]] = None,
):
    """
    Decorator to cache function results.

    Args:
        cache: BoundedCache instance to use
        key_func: Optional function to generate cache key from args.
                  If None, uses all args as key.

    Usage:
        my_cache = BoundedCache[str, dict](max_size=50)

        @cached(my_cache)
        def fetch_data(url: str) -> dict:
            return expensive_fetch(url)
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = (args, tuple(sorted(kwargs.items())))

            result = cache.get(key)
            if result is not None:
                return result

            result = func(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper._cache = cache
        return wrapper

    return decorator


# Pre-configured caches for common use cases

def create_html_cache(
    max_size: int = 50,
    ttl_hours: float = 6,
) -> BoundedCache[str, str]:
    """Create cache for HTML content with sensible defaults."""
    return BoundedCache(
        max_size=max_size,
        ttl_seconds=ttl_hours * 3600,
        name="html_cache",
    )


def create_version_cache(
    max_size: int = 200,
    ttl_hours: float = 24,
) -> BoundedCache[Tuple[str, str], Tuple[str, str, str]]:
    """Create cache for parsed version info."""
    return BoundedCache(
        max_size=max_size,
        ttl_seconds=ttl_hours * 3600,
        name="version_cache",
    )


def create_icon_cache(
    max_size: int = 500,
) -> BoundedCache[str, Any]:
    """Create cache for icon pixmaps (no TTL - icons don't change)."""
    return BoundedCache(
        max_size=max_size,
        ttl_seconds=None,
        name="icon_cache",
    )
