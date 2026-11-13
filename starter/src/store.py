"""Persistent pgvector exact cosine search with parameterized metadata filters."""
import math
from typing import Any
from .models import Chunk


class PgVectorStore:
    FILTER_KEYS = {"chapter", "chapter_number", "language", "version"}

    def __init__(self, database_url: str, dimensions: int) -> None:
        if not isinstance(dimensions, int) or not 1 <= dimensions <= 16000:
            raise ValueError("Invalid embedding dimensions")
        self.database_url = database_url
        self.dimensions = dimensions

    def connect(self):
        import psycopg
        return psycopg.connect(self.database_url, connect_timeout=5)

    def vector_literal(self, vector: list[float]) -> str:
        if len(vector) != self.dimensions or not all(math.isfinite(v) for v in vector):
            raise ValueError("Non-finite vector or incompatible dimensions")
        if not any(v != 0 for v in vector):
            raise ValueError("Cosine search requires a nonzero vector")
        return "[" + ",".join(str(float(v)) for v in vector) + "]"

    def create_schema(self) -> None:
        from psycopg import sql
        with self.connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(sql.SQL("""CREATE TABLE IF NOT EXISTS day6_chunks (
                strategy text NOT NULL, chunk_id text NOT NULL,
                document_id text NOT NULL, source text NOT NULL, page integer NOT NULL,
                content text NOT NULL, metadata jsonb NOT NULL, embedding vector({}),
                PRIMARY KEY (strategy, chunk_id))""").format(sql.Literal(self.dimensions)))
            actual = conn.execute("""SELECT format_type(atttypid, atttypmod)
                FROM pg_attribute WHERE attrelid='day6_chunks'::regclass
                AND attname='embedding'""").fetchone()[0]
            if actual != f"vector({self.dimensions})":
                raise ValueError(f"Existing table has {actual}; use matching model/database")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Atomically replace a strategy's complete snapshot, removing obsolete chunks."""
        from psycopg.types.json import Jsonb
        if not chunks or len(chunks) != len(vectors):
            raise ValueError("Need one vector per chunk and nonempty corpus")
        if len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError("Duplicate chunk IDs")
        rows = [(strategy, c.chunk_id, c.document_id, c.source, c.page, c.text,
                 Jsonb(c.metadata), self.vector_literal(v)) for c, v in zip(chunks, vectors)]
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("day6:" + strategy,))
            conn.execute("DELETE FROM day6_chunks WHERE strategy=%s", (strategy,))
            with conn.cursor() as cur:
                cur.executemany("""INSERT INTO day6_chunks
                    (strategy,chunk_id,document_id,source,page,content,metadata,embedding)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)""", rows)

    def count(self, strategy: str) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT count(*) FROM day6_chunks WHERE strategy=%s", (strategy,)).fetchone()[0]

    def versions(self) -> dict:
        with self.connect() as conn:
            row = conn.execute("""SELECT current_setting('server_version'), extversion
                FROM pg_extension WHERE extname='vector'""").fetchone()
            return {"postgresql": row[0], "pgvector": row[1], "search": "exact", "metric": "cosine"}

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from psycopg.types.json import Jsonb
        if top_k < 1 or set(filters or {}) - self.FILTER_KEYS:
            raise ValueError("Invalid top_k/filter")
        vector = self.vector_literal(query_vector)
        with self.connect() as conn:
            rows = conn.execute("""SELECT chunk_id,document_id,source,page,content,metadata,
                1 - (embedding <=> %s::vector) AS score
                FROM day6_chunks WHERE strategy=%s AND metadata @> %s
                ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s""",
                (vector, strategy, Jsonb(filters or {}), vector, top_k)).fetchall()
        return [{"chunk_id": r[0], "document_id": r[1], "source": r[2], "page": r[3],
                 "text": r[4], "metadata": r[5], "score": float(r[6])} for r in rows]
