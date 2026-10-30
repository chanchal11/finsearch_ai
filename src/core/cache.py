from __future__ import annotations

import functools
import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from cachetools import TTLCache

P = ParamSpec("P")
R = TypeVar("R")


class ICacheProvider(ABC):
    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def entries(self) -> list[dict[str, Any]]: ...


class InMemoryTTLCache(ICacheProvider):
    """Thread-safe enough for Streamlit/FastAPI dev workloads via a single process cache."""

    def __init__(self, maxsize: int = 512, default_ttl: int = 3600) -> None:
        self._default_ttl = default_ttl
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=default_ttl)
        self._custom_ttl: dict[str, int] = {}

    def get(self, key: str) -> Any | None:
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if ttl is not None and ttl != self._default_ttl:
            self._custom_ttl[key] = ttl
        self._cache[key] = value

    def delete(self, key: str) -> None:
        self._custom_ttl.pop(key, None)
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._custom_ttl.clear()
        self._cache.clear()

    def entries(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key in list(self._cache.keys()):
            rows.append(
                {
                    "key": key,
                    "ttl_seconds": self._custom_ttl.get(key, self._default_ttl),
                    "preview": _preview_value(self._cache.get(key)),
                }
            )
        return rows


def _preview_value(value: Any, max_len: int = 120) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _cache_key(prefix: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    payload = {"args": args, "kwargs": kwargs}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    return f"{prefix}:{digest}"


def tool_kv_cache(
    cache: ICacheProvider,
    *,
    prefix: str,
    ttl: int | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that memoizes pure tool fetch functions keyed by arguments."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = _cache_key(prefix, args, kwargs)
            hit = cache.get(key)
            if hit is not None:
                return hit  # type: ignore[return-value]
            result = func(*args, **kwargs)
            cache.set(key, result, ttl=ttl)
            return result

        return wrapper

    return decorator
