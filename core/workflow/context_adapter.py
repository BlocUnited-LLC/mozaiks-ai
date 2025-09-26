"""Runtime-safe context variables adapter.

Provides a unified container interface independent of AG2's internal implementation.
If the vendor ContextVariables class is missing methods or unavailable, falls back
to a simple dict-backed version with the same minimal API surface.

Public factory: create_context_container(initial: Optional[dict]) -> object
Returned object supports:
  .get(key, default=None)
  .set(key, value)
  .remove(key) -> bool
  .keys() -> Iterable[str]
  .contains(key) -> bool
  .data (property) -> underlying dict (for logging only)
"""
from __future__ import annotations
from typing import Any, Iterable

try:  # pragma: no cover - vendor optional
    from autogen.agentchat.group import ContextVariables as VendorContextVariables  # type: ignore
except Exception:  # pragma: no cover
    VendorContextVariables = None  # type: ignore


class _RuntimeContextVariables:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(initial or {})

    def get(self, key: str, default: Any | None = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def remove(self, key: str) -> bool:
        return self._data.pop(key, None) is not None

    def keys(self) -> Iterable[str]:  # noqa: D401
        return self._data.keys()

    def contains(self, key: str) -> bool:
        return key in self._data

    @property
    def data(self) -> dict[str, Any]:  # for logging only
        return self._data


def _vendor_is_usable(obj: Any) -> bool:
    required = ("get", "set", "remove", "keys", "contains")
    return all(hasattr(obj, n) for n in required)


def create_context_container(initial: dict[str, Any] | None = None):
    if VendorContextVariables:
        try:
            inst = VendorContextVariables(data=initial or {})  # type: ignore[call-arg]
            if _vendor_is_usable(inst):
                return inst
        except Exception:
            pass
    return _RuntimeContextVariables(initial=initial)

__all__ = ["create_context_container"]
