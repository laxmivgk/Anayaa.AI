#!/usr/bin/env python3
"""One-time seed: load scriptures into PostgreSQL and Milvus."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.memory.milvus_store import MilvusStore
from app.memory.postgres import PostgresPool
from app.retrieval.corpus import load_scriptures_json

CORPUS_SEED_VERSION = "scriptures_v1"


def corpus_checksum(corpus) -> str:
    return hashlib.sha256(json.dumps([v.to_dict() for v in corpus]).encode()).hexdigest()[:16]


def corpus_status_rebuild_reasons(status, corpus_count: int, checksum: str) -> list[str]:
    if not status:
        return ["corpus status is missing"]

    reasons = []
    if not status.get("ready"):
        reasons.append("corpus status is not ready")
    if status.get("verse_count") != corpus_count:
        reasons.append(f"verse count changed ({status.get('verse_count')} -> {corpus_count})")
    if status.get("seed_version") != CORPUS_SEED_VERSION:
        reasons.append(f"seed version changed ({status.get('seed_version')} -> {CORPUS_SEED_VERSION})")
    if status.get("seed_checksum") != checksum:
        reasons.append("corpus checksum changed")
    return reasons


async def get_existing_corpus_status(pg: PostgresPool) -> dict | None:
    row = await pg.fetchrow(
        """
        SELECT ready, verse_count, seed_version, seed_checksum
        FROM corpus_status
        WHERE id = 1
        """
    )
    return dict(row) if row else None


async def seed_postgres(pg: PostgresPool, corpus, checksum: str) -> int:
    for verse in corpus:
        await pg.execute(
            """
            INSERT INTO scriptures (id, faith, source, chapter, verse, original_text, translation, context, keywords, milvus_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $1)
            ON CONFLICT (id) DO UPDATE SET
                faith = EXCLUDED.faith,
                source = EXCLUDED.source,
                chapter = EXCLUDED.chapter,
                verse = EXCLUDED.verse,
                original_text = EXCLUDED.original_text,
                translation = EXCLUDED.translation,
                context = EXCLUDED.context,
                keywords = EXCLUDED.keywords,
                milvus_id = EXCLUDED.milvus_id
            """,
            verse.id,
            verse.faith,
            verse.source,
            verse.chapter,
            verse.verse,
            verse.original_text,
            verse.translation,
            verse.context,
            verse.keywords,
        )
        for kw in verse.keywords:
            entity_id = await pg.fetchval(
                """
                INSERT INTO kg_entities (entity_type, name, faith)
                VALUES ('concept', $1, $2)
                ON CONFLICT (entity_type, name, faith) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                kw,
                verse.faith,
            )
            src_id = await pg.fetchval(
                """
                INSERT INTO kg_entities (entity_type, name, faith)
                VALUES ('source', $1, $2)
                ON CONFLICT (entity_type, name, faith) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                verse.source,
                verse.faith,
            )
            if entity_id and src_id:
                await pg.execute(
                    """
                    INSERT INTO kg_edges (from_entity_id, to_entity_id, relation, scripture_id)
                    SELECT $1, $2, 'teaches', $3
                    WHERE NOT EXISTS (
                        SELECT 1 FROM kg_edges e
                        WHERE e.from_entity_id = $1 AND e.to_entity_id = $2 AND e.scripture_id = $3
                    )
                    """,
                    src_id,
                    entity_id,
                    verse.id,
                )

    await pg.execute(
        """
        INSERT INTO corpus_status (id, ready, verse_count, last_seed_at, seed_version, seed_checksum)
        VALUES (1, TRUE, $1, NOW(), $2, $3)
        ON CONFLICT (id) DO UPDATE SET
            ready = EXCLUDED.ready,
            verse_count = EXCLUDED.verse_count,
            last_seed_at = EXCLUDED.last_seed_at,
            seed_version = EXCLUDED.seed_version,
            seed_checksum = EXCLUDED.seed_checksum
        """,
        len(corpus),
        CORPUS_SEED_VERSION,
        checksum,
    )
    return len(corpus)


def seed_milvus(corpus, force_recreate: bool = False) -> tuple[int, bool]:
    settings = get_settings()
    if not settings.milvus_enabled:
        raise RuntimeError("MILVUS_ENABLED must be true. Milvus is required for retrieval.")

    store = MilvusStore()
    store.connect()

    existing = store.entity_count()
    recreate = force_recreate or existing != len(corpus)
    count = store.seed_verses(corpus, recreate=recreate)
    hybrid = store.hybrid_enabled
    store.close()
    return count, hybrid


async def main() -> None:
    settings = get_settings()
    corpus = load_scriptures_json()
    checksum = corpus_checksum(corpus)

    pg = PostgresPool(settings.postgres_dsn)
    await pg.connect()
    try:
        existing_status = await get_existing_corpus_status(pg)
        rebuild_reasons = corpus_status_rebuild_reasons(existing_status, len(corpus), checksum)
        if rebuild_reasons:
            print("[anayaa] Corpus status changed; rebuilding Milvus embeddings:")
            for reason in rebuild_reasons:
                print(f"[anayaa]   - {reason}")
        else:
            print("[anayaa] Corpus status matches local scripture corpus.")

        pg_count = await seed_postgres(pg, corpus, checksum)
        print(f"Seeded {pg_count} verses from the Anayaa scripture corpus into PostgreSQL (checksum={checksum}).")

        if not settings.milvus_enabled:
            raise RuntimeError("MILVUS_ENABLED must be true. Milvus is required for retrieval.")
        try:
            milvus_count, hybrid = seed_milvus(corpus, force_recreate=bool(rebuild_reasons))
        except RuntimeError as exc:
            print("[anayaa] ERROR: Milvus Lite could not start or connect for retrieval seeding.", file=sys.stderr)
            print(f"[anayaa]   {exc}", file=sys.stderr)
            print("[anayaa]   Close any running Anayaa backend/MCP process, then retry setup.", file=sys.stderr)
            print("[anayaa]   If you recently cleaned resources, run: ./scripts/free-resources.sh --storage --yes", file=sys.stderr)
            print("[anayaa]   If the error mentions socket bind or Operation not permitted, run setup from a normal macOS Terminal window.", file=sys.stderr)
            raise SystemExit(1) from None
        mode = "HNSW+BM25 hybrid" if hybrid else "dense HNSW"
        print(f"Seeded {milvus_count} verse embeddings into Milvus ({mode}).")

    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
