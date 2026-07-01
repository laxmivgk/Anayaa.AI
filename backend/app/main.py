import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, query, system
from app.auth.session import SessionManager
from app.auth.users import ensure_users_table
from app.config import get_settings
from app.memory.milvus_store import MilvusStore
from app.memory.postgres import PostgresPool
from app.memory.redis_cache import RedisCache
from app.privacy.retention import retention_loop
from app.retrieval.corpus import load_scriptures_json
from app.retrieval.embeddings import get_embedder
from app.llm.generator import prewarm_ollama_models

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pg = PostgresPool(settings.postgres_dsn)
    redis = RedisCache(settings.redis_url)
    if not settings.postgres_enabled:
        raise RuntimeError("POSTGRES_ENABLED must be true. PostgreSQL is required.")
    await pg.connect()
    await ensure_users_table(pg)
    await redis.connect()
    load_scriptures_json()
    corpus = load_scriptures_json()
    get_embedder().embed_query("compassion conflict duty")
    await prewarm_ollama_models()

    milvus = MilvusStore(settings.milvus_uri)
    if not settings.milvus_enabled:
        raise RuntimeError("MILVUS_ENABLED must be true. Milvus is required for retrieval.")
    try:
        milvus.connect()
        milvus_entities = milvus.entity_count()
        if milvus_entities <= 0:
            raise RuntimeError("Milvus collection is empty. Run `cd backend && python scripts/seed_milvus.py` before starting the API.")
        milvus_status = {
            "available": True,
            "entities": milvus_entities,
            "hybrid": bool(milvus.hybrid_enabled),
            "collection": settings.milvus_collection,
        }
    finally:
        milvus.close()

    count = len(corpus)
    await pg.execute(
        """
        UPDATE corpus_status SET ready = TRUE, verse_count = $1, last_seed_at = NOW(), seed_version = 'scriptures_v1'
        WHERE id = 1
        """,
        count,
    )

    app.state.pg = pg
    app.state.redis = redis
    app.state.milvus = None
    app.state.milvus_status = milvus_status
    app.state.session_mgr = SessionManager(redis)
    retention_task = asyncio.create_task(retention_loop(pg, settings))
    try:
        yield
    finally:
        if retention_task:
            retention_task.cancel()
            with suppress(asyncio.CancelledError):
                await retention_task
        from app.mcp.client import close_mcp_client
        await close_mcp_client()
        await redis.close()
        await pg.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Anayaa.AI", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(query.router)
    app.include_router(system.router)

    if FRONTEND_DIST.exists():
        assets_dir = FRONTEND_DIST / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_frontend(full_path: str):
            requested = FRONTEND_DIST / full_path
            if full_path and requested.is_file():
                return FileResponse(requested)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
