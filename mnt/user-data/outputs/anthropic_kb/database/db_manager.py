"""
Database Manager
Handles all persistence: PostgreSQL for structured metadata,
ChromaDB for vector embeddings and semantic search.
"""

import json
import uuid
from datetime import datetime
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger("database_manager")


class DatabaseManager:
    """
    Dual-database manager:
    - PostgreSQL: Structured metadata, relationships, full-text search
    - ChromaDB:   Vector embeddings for semantic search
    
    Falls back to SQLite if PostgreSQL is not available.
    """

    def __init__(self, config: dict):
        self.config = config
        self.use_postgres = config.get("use_postgres", False)
        self.pg_conn = None
        self.chroma_client = None
        self.collection = None
        self.sqlite_conn = None

    async def initialize(self):
        """Initialize both databases and create schemas."""
        await self._init_vector_db()
        await self._init_relational_db()
        logger.info("Database initialized (Vector DB + Relational DB)")

    async def _init_vector_db(self):
        """Initialize ChromaDB for semantic search."""
        try:
            import chromadb
            from chromadb.config import Settings

            persist_dir = self.config.get("chroma_persist_dir", "./chroma_db")
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
        except ImportError:
            logger.warning("ChromaDB not installed, using in-memory fallback")
            self._memory_store = []
        except Exception as e:
            logger.warning(f"ChromaDB init error: {e}, using in-memory fallback")
            self._memory_store = []

    async def _init_relational_db(self):
        """Initialize SQLite (default) or PostgreSQL."""
        if self.use_postgres:
            await self._init_postgres()
        else:
            await self._init_sqlite()

    async def _init_sqlite(self):
        """Initialize SQLite database with full schema."""
        import sqlite3
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

            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT DEFAULT CURRENT_TIMESTAMP,
                docs_ingested INTEGER,
                docs_categorized INTEGER,
                docs_indexed INTEGER,
                errors INTEGER,
                duration_seconds REAL
            );

            CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain);
            CREATE INDEX IF NOT EXISTS idx_documents_content_type ON documents(content_type);
            CREATE INDEX IF NOT EXISTS idx_documents_importance ON documents(importance_score);
            CREATE INDEX IF NOT EXISTS idx_capability_tags_tag ON capability_tags(tag);
            CREATE INDEX IF NOT EXISTS idx_model_refs ON model_version_refs(model_version);

            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title, summary, content, content='documents', content_rowid='rowid'
            );
        """)
        self.sqlite_conn.commit()
        logger.info(f"SQLite database initialized at {db_path}")

    async def _init_postgres(self):
        """Initialize PostgreSQL with full schema."""
        try:
            import asyncpg
            self.pg_conn = await asyncpg.connect(self.config["postgres_dsn"])
            await self.pg_conn.execute("""
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
                    key_facts JSONB,
                    capability_tags TEXT[],
                    model_versions TEXT[],
                    audience TEXT,
                    importance_score INTEGER DEFAULT 5,
                    date_context TEXT,
                    metadata JSONB,
                    scraped_at TIMESTAMPTZ,
                    categorized_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain);
                CREATE INDEX IF NOT EXISTS idx_documents_importance ON documents(importance_score DESC);
                CREATE INDEX IF NOT EXISTS idx_gin_tags ON documents USING GIN(capability_tags);
            """)
            logger.info("PostgreSQL database initialized")
        except Exception as e:
            logger.error(f"PostgreSQL init failed: {e}, falling back to SQLite")
            self.use_postgres = False
            await self._init_sqlite()

    async def store_document(self, document: dict):
        """Store a categorized document in both databases."""
        doc_id = document.get("id", str(uuid.uuid4()))

        # Store in relational DB
        if self.use_postgres:
            await self._store_postgres(doc_id, document)
        else:
            self._store_sqlite(doc_id, document)

        # Store in vector DB
        await self._store_vector(doc_id, document)

    def _store_sqlite(self, doc_id: str, doc: dict):
        """Store document in SQLite."""
        cursor = self.sqlite_conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO documents 
                (id, url, title, content, content_hash, doc_type, source_category,
                 domain, subdomain, content_type, summary, audience, importance_score,
                 date_context, scraped_at, categorized_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id, doc.get("url"), doc.get("title"), doc.get("content", "")[:50000],
                doc.get("content_hash"), doc.get("doc_type"), doc.get("source_category"),
                doc.get("domain"), doc.get("subdomain"), doc.get("content_type"),
                doc.get("summary"), doc.get("audience"), doc.get("importance_score", 5),
                doc.get("date_context"), doc.get("scraped_at"), doc.get("categorized_at"),
            ))

            # Store tags
            for tag in doc.get("capability_tags", []):
                cursor.execute(
                    "INSERT OR IGNORE INTO capability_tags (document_id, tag) VALUES (?, ?)",
                    (doc_id, tag),
                )

            # Store model version references
            for version in doc.get("model_versions", []):
                cursor.execute(
                    "INSERT OR IGNORE INTO model_version_refs (document_id, model_version) VALUES (?, ?)",
                    (doc_id, version),
                )

            # Store key facts
            for i, fact in enumerate(doc.get("key_facts", [])):
                cursor.execute(
                    "INSERT INTO key_facts (document_id, fact, fact_order) VALUES (?, ?, ?)",
                    (doc_id, fact, i),
                )

            self.sqlite_conn.commit()
        except Exception as e:
            self.sqlite_conn.rollback()
            raise e

    async def _store_vector(self, doc_id: str, doc: dict):
        """Store document embedding in ChromaDB."""
        if not hasattr(self, "_memory_store") and self.collection is None:
            return

        # Use summary + title for embedding (more semantic than raw content)
        embed_text = f"{doc.get('title', '')} {doc.get('summary', '')} {' '.join(doc.get('capability_tags', []))}"

        if hasattr(self, "_memory_store"):
            # In-memory fallback
            self._memory_store.append({**doc, "_embed_text": embed_text})
        else:
            try:
                self.collection.upsert(
                    ids=[doc_id],
                    documents=[embed_text],
                    metadatas=[{
                        "url": doc.get("url", ""),
                        "title": doc.get("title", ""),
                        "domain": doc.get("domain", "other"),
                        "importance": doc.get("importance_score", 5),
                    }],
                )
            except Exception as e:
                logger.warning(f"Vector storage error for {doc_id}: {e}")

    async def semantic_search(
        self, query: str, top_k: int = 8, domain_filter: Optional[str] = None
    ) -> list:
        """Search for relevant documents using semantic similarity."""
        if hasattr(self, "_memory_store"):
            return self._memory_search(query, top_k, domain_filter)

        if self.collection is None:
            return []

        where_filter = {"domain": domain_filter} if domain_filter else None

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(top_k, max(1, self.collection.count())),
                where=where_filter,
            )
            # Fetch full documents from relational DB
            doc_ids = results["ids"][0] if results["ids"] else []
            return await self._fetch_documents_by_ids(doc_ids)
        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            return self._fallback_keyword_search(query, top_k)

    def _memory_search(self, query: str, top_k: int, domain_filter: Optional[str]) -> list:
        """Simple keyword search for in-memory fallback."""
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
        scored.sort(reverse=True)
        return [doc for _, doc in scored[:top_k]]

    def _fallback_keyword_search(self, query: str, top_k: int) -> list:
        """SQLite full-text search fallback."""
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
            logger.error(f"Keyword search error: {e}")
            return []

    async def _fetch_documents_by_ids(self, doc_ids: list) -> list:
        """Fetch full document records by IDs."""
        if not doc_ids:
            return []
        if self.sqlite_conn:
            cursor = self.sqlite_conn.cursor()
            placeholders = ",".join("?" * len(doc_ids))
            cursor.execute(
                f"SELECT * FROM documents WHERE id IN ({placeholders})", doc_ids  # nosec B608
            )
            return [dict(row) for row in cursor.fetchall()]
        return []

    async def get_statistics(self) -> dict:
        """Get comprehensive statistics about the knowledge base."""
        stats = {"total_documents": 0, "by_domain": {}, "by_content_type": {}}

        if self.sqlite_conn:
            cursor = self.sqlite_conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM documents")
            stats["total_documents"] = cursor.fetchone()[0]

            cursor.execute("SELECT domain, COUNT(*) as count FROM documents GROUP BY domain ORDER BY count DESC")
            stats["by_domain"] = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT content_type, COUNT(*) as count FROM documents GROUP BY content_type ORDER BY count DESC")
            stats["by_content_type"] = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT COUNT(DISTINCT tag) FROM capability_tags")
            stats["unique_tags"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT model_version) FROM model_version_refs")
            stats["unique_model_versions"] = cursor.fetchone()[0]

            cursor.execute("SELECT AVG(importance_score) FROM documents")
            avg = cursor.fetchone()[0]
            stats["avg_importance_score"] = round(avg, 2) if avg else 0

        if self.collection:
            stats["vector_documents"] = self.collection.count()
        elif hasattr(self, "_memory_store"):
            stats["vector_documents"] = len(self._memory_store)

        return stats

    async def export_to_json(self, output_path: str = "kb_export.json"):
        """Export the entire knowledge base to JSON."""
        if not self.sqlite_conn:
            logger.error("No database connection for export")
            return

        cursor = self.sqlite_conn.cursor()
        cursor.execute("SELECT * FROM documents ORDER BY importance_score DESC")
        docs = [dict(row) for row in cursor.fetchall()]

        # Enrich with tags and facts
        for doc in docs:
            cursor.execute(
                "SELECT tag FROM capability_tags WHERE document_id = ?", (doc["id"],)
            )
            doc["capability_tags"] = [row[0] for row in cursor.fetchall()]

            cursor.execute(
                "SELECT fact FROM key_facts WHERE document_id = ? ORDER BY fact_order",
                (doc["id"],),
            )
            doc["key_facts"] = [row[0] for row in cursor.fetchall()]

        with open(output_path, "w") as f:
            json.dump({"exported_at": datetime.now().isoformat(), "documents": docs}, f, indent=2)

        logger.info(f"Exported {len(docs)} documents to {output_path}")
        return output_path

    def close(self):
        """Close all database connections."""
        if self.sqlite_conn:
            self.sqlite_conn.close()
        if self.pg_conn:
            self.pg_conn.close()
        if self.chroma_client:
            try:
                self.chroma_client.persist()
            except Exception:
                pass
