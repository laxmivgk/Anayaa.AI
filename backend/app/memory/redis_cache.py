import json
from typing import Any

try:
    import redis.asyncio as redis
except ImportError:
    redis = None


class RedisCache:
    def __init__(self, url: str):
        self.url = url
        self._client: Any = None

    async def connect(self) -> None:
        if redis is None:
            raise RuntimeError("redis package is required; install backend dependencies before starting the API.")
        try:
            self._client = redis.from_url(self.url, decode_responses=True)
            await self._client.ping()
        except Exception as exc:
            self._client = None
            raise RuntimeError(f"Redis is required but unavailable at {self.url}.") from exc

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    async def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        payload = json.dumps(value)
        if not self._client:
            raise RuntimeError("Redis client is not connected.")
        if ttl_seconds:
            await self._client.setex(key, ttl_seconds, payload)
        else:
            await self._client.set(key, payload)

    async def get_json(self, key: str) -> Any | None:
        if not self._client:
            raise RuntimeError("Redis client is not connected.")
        raw = await self._client.get(key)
        return json.loads(raw) if raw else None

    async def delete(self, key: str) -> None:
        if not self._client:
            raise RuntimeError("Redis client is not connected.")
        await self._client.delete(key)

    async def incr(self, key: str) -> int:
        if not self._client:
            raise RuntimeError("Redis client is not connected.")
        return int(await self._client.incr(key))

    async def expire(self, key: str, seconds: int) -> None:
        if not self._client:
            raise RuntimeError("Redis client is not connected.")
        await self._client.expire(key, seconds)

    async def ping(self) -> bool:
        if not self._client:
            return False
        try:
            return bool(await self._client.ping())
        except Exception:
            return False
