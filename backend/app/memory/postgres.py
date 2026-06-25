import sys
import warnings
from typing import Any

try:
    import asyncpg
except ImportError:
    asyncpg = None

# ---------------------------------------------------------------------------
# asyncpg Cython shutdown workaround
# ---------------------------------------------------------------------------
# During Python interpreter shutdown, Cython C extensions are unloaded before
# Python's GC finalizes remaining objects. This causes two known errors:
#
#   1. AttributeError: 'Connection' object has no attribute '_aborted'
#      (from Connection.__del__ -> is_closed() accessing freed C struct)
#
#   2. TypeError: no default __reduce__ due to non-trivial __cinit
#      (from Cython __reduce_cython__ during module cleanup/copyreg)
#
# These patches suppress both by intercepting the failing calls.

if asyncpg is not None:
    # ---- Patch 1: Connection.__del__ ----
    _orig_conn_del = asyncpg.connection.Connection.__del__

    def _safe_conn_del(self: asyncpg.connection.Connection) -> None:
        try:
            _orig_conn_del(self)
        except (AttributeError, TypeError):
            pass

    asyncpg.connection.Connection.__del__ = _safe_conn_del

    # ---- Patch 2: Suppress __reduce_cython__ on Cython types in pgproto ----
    # During shutdown, Python's copyreg may try to pickle Cython extension
    # types (ReadBuffer, WriteBuffer, CodecContext, etc.) whose __cinit__
    # state is already freed -> TypeError: no default __reduce__ due to
    # non-trivial __cinit. We silence these by patching __reduce__
    # (which is aliased to __reduce_cython__ by Cython) to return a safe
    # no-op pickle.
    #
    # Note: we cannot use hasattr() to detect __reduce_cython__ here because:
    #   - Python 3's hasattr() returns False when the attribute raises
    #     any exception (see https://bugs.python.org/msg227219).
    #   - Cython's __reduce_cython__ is a property getter that actually
    #     *throws* the TypeError we are trying to suppress when accessing
    #     it on instances of types with non-trivial __cinit__.
    #   - So hasattr(x, '__reduce_cython__') returns False for the very
    #     types we need to patch (ReadBuffer, WriteBuffer).
    #   - Instead we iterate known problematic types + any types that
    #     have a __reduce__ attribute pointing to __reduce_cython__.
    try:
        import asyncpg.pgproto.pgproto as _pgproto
        import types as _types

        # Collect candidates: start with known problematic types
        _candidates = set()
        for _name in ('ReadBuffer', 'WriteBuffer', 'CodecContext', '__UUIDReplaceMe'):
            _obj = getattr(_pgproto, _name, None)
            if _obj is not None and isinstance(_obj, type):
                _candidates.add(_obj)

        # Also check all types in the module whose __reduce__ is a
        # method (i.e. __reduce_cython__ bound as __reduce__)
        for _name in dir(_pgproto):
            _obj = getattr(_pgproto, _name)
            if isinstance(_obj, type):
                _red = getattr(_obj, '__reduce__', None)
                if _red and isinstance(_red, _types.MethodType):
                    # This __reduce__ is likely __reduce_cython__; try it
                    try:
                        _red(_obj())
                    except TypeError:
                        # Bingo — this is the type we need to patch
                        _candidates.add(_obj)
                    except Exception:
                        pass

        for _cls in _candidates:
            def _safe_reduce(self, cls=_cls):
                return (cls.__new__, (cls(),), {})
            _cls.__reduce__ = _safe_reduce
            # __setstate_cython__ also needs to be neutralised
            _setstate = getattr(_cls, '__setstate_cython__', None)
            if _setstate is not None:
                _cls.__setstate_cython__ = staticmethod(lambda self, state: None)
    except Exception:
        pass


class PostgresPool:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Any = None
        self.available = False

    async def connect(self) -> None:
        if asyncpg is None:
            raise RuntimeError("asyncpg is required; install backend dependencies before starting the API.")
        try:
            self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5, timeout=5)
            self.available = True
        except Exception as exc:
            self.pool = None
            self.available = False
            raise RuntimeError("PostgreSQL is required but unavailable. Run scripts/setup_postgres.sh and verify backend/.env.") from exc

    async def close(self) -> None:
        if self.pool:
            # Terminate first to immediately abort all connections,
            # preventing orphaned Connection objects from triggering
            # Cython __del__ errors ("no attribute '_aborted'") during GC
            try:
                self.pool.terminate()
            except Exception:
                pass
            try:
                await self.pool.close()
            except Exception:
                pass
        self.pool = None
        self.available = False

    async def fetchval(self, query: str, *args: Any) -> Any:
        if not self.pool:
            raise RuntimeError("PostgreSQL pool is not connected.")
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        if not self.pool:
            raise RuntimeError("PostgreSQL pool is not connected.")
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        if not self.pool:
            raise RuntimeError("PostgreSQL pool is not connected.")
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def is_corpus_ready(self) -> bool:
        val = await self.fetchval("SELECT ready FROM corpus_status WHERE id = 1")
        return bool(val)

    async def get_corpus_status(self) -> dict[str, Any]:
        row = await self.fetchrow(
            "SELECT ready, verse_count, last_seed_at, seed_version FROM corpus_status WHERE id = 1"
        )
        if not row:
            return {"ready": False, "verse_count": 0}
        return dict(row)

    async def fetchrow(self, query: str, *args: Any) -> Any:
        if not self.pool:
            raise RuntimeError("PostgreSQL pool is not connected.")
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
