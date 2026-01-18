"""Shared backend HTTP client for workflow tools.

This is intentionally NOT part of the runtime core.

Why:
- The Mozaiks backend APIs (repo/deploy/db management, etc.) are platform-specific.
- Keeping this in `workflows/_shared` lets the runtime stay open-source-friendly,
  while workflow packs can remain proprietary or optional.

Auth:
- Uses `X-Internal-Api-Key` header from env var `INTERNAL_API_KEY`.
- Base URL comes from `MOZAIKS_BACKEND_URL`.
"""

import os
from typing import Any, Dict, Optional

import aiohttp

from logs.logging_config import get_core_logger

logger = get_core_logger("backend_client")


class BackendClient:
    def __init__(self):
        # Keep defaults aligned with `core.core_config`.
        self.base_url = os.getenv("MOZAIKS_BACKEND_URL", "https://api.mozaiks.ai").strip().rstrip("/")
        self.api_key = os.getenv("INTERNAL_API_KEY", "").strip()

        if not self.api_key:
            logger.warning("INTERNAL_API_KEY not set. Backend calls may fail.")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Internal-Api-Key": self.api_key,
            "Accept": "application/json",
        }

    async def _handle_response(self, resp: aiohttp.ClientResponse, error_msg: str) -> Dict[str, Any]:
        if resp.status not in (200, 201):
            text = await resp.text()
            logger.error(f"{error_msg}: {resp.status} {text}")
            raise RuntimeError(f"{error_msg}: {resp.status} {text}")
        return await resp.json()

    async def get(self, endpoint: str, params: Optional[Dict] = None, error_msg: str = "Request failed") -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=self._get_headers()) as resp:
                return await self._handle_response(resp, error_msg)

    async def post(
        self,
        endpoint: str,
        json: Optional[Dict] = None,
        data: Any = None,
        error_msg: str = "Request failed",
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        # If data is provided (e.g. FormData), let aiohttp handle Content-Type
        if data is not None:
            headers.pop("Content-Type", None)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json, data=data, headers=headers) as resp:
                return await self._handle_response(resp, error_msg)

    async def put(self, endpoint: str, json: Optional[Dict] = None, error_msg: str = "Request failed") -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.put(url, json=json, headers=self._get_headers()) as resp:
                return await self._handle_response(resp, error_msg)

    async def delete(self, endpoint: str, error_msg: str = "Request failed") -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=self._get_headers()) as resp:
                return await self._handle_response(resp, error_msg)


# Singleton instance (convenience)
backend_client = BackendClient()
