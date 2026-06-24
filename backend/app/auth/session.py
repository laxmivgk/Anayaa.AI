from datetime import datetime, timezone

from app.memory.redis_cache import RedisCache


class SessionManager:
    def __init__(self, redis: RedisCache):
        self.redis = redis

    async def register_session(self, session_id: str, email: str, ttl_seconds: int) -> None:
        await self.redis.set_json(
            f"session:{session_id}",
            {"email": email, "created_at": datetime.now(timezone.utc).isoformat()},
            ttl_seconds,
        )

    async def is_session_active(self, session_id: str, email: str) -> bool:
        data = await self.redis.get_json(f"session:{session_id}")
        if not data:
            return False
        return data.get("email") == email

    async def revoke_session(self, session_id: str) -> None:
        await self.redis.delete(f"session:{session_id}")

    async def check_rate_limit(self, session_id: str, limit: int) -> bool:
        key = f"rate:{session_id}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 60)
        return count <= limit
