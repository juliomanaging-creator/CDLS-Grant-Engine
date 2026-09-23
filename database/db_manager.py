"""
Database Manager
Handles all persistence: SQLite for metadata, ChromaDB for vector embeddings.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Optional

try:
    from logger import setup_logger  # type: ignore
    logger = setup_logger("database_manager")
except ImportError:
    try:
        from utils.logger import setup_logger  # type: ignore
        logger = setup_logger("database_manager")
    except ImportError:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger("database_manager")


class DatabaseManager:
    """Manages SQLite structured records and ChromaDB vector embeddings."""

    def __init__(self, config: dict):
        self.config = config
        self.use_postgres: bool = config.get("use_postgres", False)
        self.pg_conn: Any = None
        self.chroma_client: Any = None
        self.collection: Any = None
        self.sqlite_conn: Optional[sqlite3.Connection] = None
        self._memory_store: list[dict] = []

    async def initialize(self):
        await self._init_vector_db()
        await self._init_relational_db()
        logger.info("Database initialized (Vector DB + Relational DB)")

    async def _init_vector_db(self):
        try:
            import chromadb

            persist_dir = self.config.get("chroma_persist_dir", "./chroma_db")

            try:
                self.chroma_client = chromadb.PersistentClient(path=persist_dir)
            except (AttributeError, TypeError):
                from chromadb.config import Settings
                self.chroma_client = chromadb.Client(
                    Settings(
                        chroma_db_impl="duckdb+parquet",
                        persist_directory=persist_dir,
                        anonymized_telemetry=False,
                    )
                )

            self.collection = self.chroma_client.get_or_create_collection(
                name="anthropic_kb",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"ChromaDB initialized with {self.collection.count()} existing documents")
        except Exception as e:
            logger.warning(f"ChromaDB initialization notice ({e}). Using memory store.")
            self.collection = None

    async def _init_relational_db(self):
        db_path = self.config.get("sqlite_path", "./anthropic_kb.db")
        self.sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
        self.sqlite_conn.row_factory = sqlite3.Row
        cursor = self.sqlite_conn.cursor()

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                content TEXT,
                content_hash TEXT,
                doc_type TEXT,
                source_category TEXT,
                domain TEXT,
                subdomain TEXT,
                content_type TEXT,
                summary TEXT,
                audience TEXT,
                importance_score INTEGER DEFAULT 5,
                date_context TEXT,
                categorization_method TEXT,
                scraped_at TEXT,
                categorized_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS capability_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT REFERENCES documents(id),
                tag TEXT NOT NULL,
                UNIQUE(document_id, tag)
            );

            CREATE TABLE IF NOT EXISTS model_version_refs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT REFERENCES documents(id),
                model_version TEXT NOT NULL,
                UNIQUE(document_id, model_version)
            );

            CREATE TABLE IF NOT EXISTS key_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT REFERENCES documents(id),
                fact TEXT NOT NULL,
                fact_order INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain);
            CREATE INDEX IF NOT EXISTS idx_documents_importance ON documents(importance_score);
        """)
        self.sqlite_conn.commit()

    async def store_document(self, document: dict):
        doc_id = document.get("id", str(uuid.uuid4()))
        self._store_sqlite(doc_id, document)
        await self._store_vector(doc_id, document)

    def _store_sqlite(self, doc_id: str, doc: dict):
        if self.sqlite_conn is None:
            return
        cursor = self.sqlite_conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO documents 
                (id, url, title, content, content_hash, doc_type, source_category,
                 domain, subdomain, content_type, summary, audience, importance_score,
                 date_context, scraped_at, categorized_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id, doc.get("url"), doc.get("title"), str(doc.get("content", ""))[:50000],
                doc.get("content_hash"), doc.get("doc_type"), doc.get("source_category"),
                doc.get("domain"), doc.get("subdomain"), doc.get("content_type"),
                doc.get("summary"), doc.get("audience"), doc.get("importance_score", 5),
                doc.get("date_context"), doc.get("scraped_at"), doc.get("categorized_at"),
            ))

            for tag in doc.get("capability_tags", []):
                cursor.execute(
                    "INSERT OR IGNORE INTO capability_tags (document_id, tag) VALUES (?, ?)",
                    (doc_id, tag),
                )

            for version in doc.get("model_versions", []):
                cursor.execute(
                    "INSERT OR IGNORE INTO model_version_refs (document_id, model_version) VALUES (?, ?)",
                    (doc_id, version),
                )

            for i, fact in enumerate(doc.get("key_facts", [])):
                cursor.execute(
                    "INSERT INTO key_facts (document_id, fact, fact_order) VALUES (?, ?, ?)",
                    (doc_id, str(fact), i),
                )

            self.sqlite_conn.commit()
        except Exception as e:
            if self.sqlite_conn:
                self.sqlite_conn.rollback()
            raise e

    async def _store_vector(self, doc_id: str, doc: dict):
        embed_text = f"{doc.get('title', '')} {doc.get('summary', '')} {' '.join(doc.get('capability_tags', []))}"

        if self.collection is None:
            self._memory_store.append({**doc, "_embed_text": embed_text})
            return

        try:
            self.collection.upsert(
                ids=[doc_id],
                documents=[embed_text],
                metadatas=[{
                    "url": str(doc.get("url", "")),
                    "title": str(doc.get("title", "")),
                    "domain": str(doc.get("domain", "other")),
                    "importance": int(doc.get("importance_score", 5)),
                }],
            )
        except Exception as e:
            logger.warning(f"Vector storage notice for {doc_id}: {e}")

    async def semantic_search(
        self, query: str, top_k: int = 8, domain_filter: Optional[str] = None
    ) -> list:
        if self.collection is None:
            return self._memory_search(query, top_k, domain_filter)

        where_filter: Any = {"domain": domain_filter} if domain_filter else None

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(top_k, max(1, self.collection.count())),
                where=where_filter,
            )
            doc_ids = results["ids"][0] if results.get("ids") and results["ids"] else []
            return await self._fetch_documents_by_ids(doc_ids)
        except Exception as e:
            logger.error(f"Semantic search fallback: {e}")
            return self._fallback_keyword_search(query, top_k)

    def _memory_search(self, query: str, top_k: int, domain_filter: Optional[str]) -> list:
        query_lower = query.lower()
        scored = []
        for doc in self._memory_store:
            if domain_filter and doc.get("domain") != domain_filter:
                continue
            score = sum(
                1 for word in query_lower.split()
                if word in doc.get("_embed_text", "").lower()
            )
            if score > 0:
                scored.append((score, doc))

        # Safe key-based sort avoids dict comparison errors
        scored.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]

    def _fallback_keyword_search(self, query: str, top_k: int) -> list:
        if not self.sqlite_conn:
            return []
        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute("""
                SELECT d.* FROM documents d
                WHERE d.content LIKE ? OR d.title LIKE ? OR d.summary LIKE ?
                ORDER BY d.importance_score DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", top_k))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Keyword search notice: {e}")
            return []

    async def _fetch_documents_by_ids(self, doc_ids: list) -> list:
        if not doc_ids or not self.sqlite_conn:
            return []
        cursor = self.sqlite_conn.cursor()
        placeholders = ",".join("?" * len(doc_ids))
        cursor.execute(
            f"SELECT * FROM documents WHERE id IN ({placeholders})", doc_ids  # nosec B608
        )
        return [dict(row) for row in cursor.fetchall()]

    async def get_statistics(self) -> dict:
        stats = {"total_documents": 0, "by_domain": {}, "by_content_type": {}}
        if self.sqlite_conn:
            cursor = self.sqlite_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM documents")
            stats["total_documents"] = cursor.fetchone()[0]

            cursor.execute("SELECT domain, COUNT(*) FROM documents GROUP BY domain ORDER BY COUNT(*) DESC")
            stats["by_domain"] = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT content_type, COUNT(*) FROM documents GROUP BY content_type ORDER BY COUNT(*) DESC")
            stats["by_content_type"] = {row[0]: row[1] for row in cursor.fetchall()}

        if self.collection:
            stats["vector_documents"] = self.collection.count()
        else:
            stats["vector_documents"] = len(self._memory_store)
        return stats