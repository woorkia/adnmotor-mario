import sqlite3
import logging
import os
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Devuelve conexión con WAL mode para acceso seguro."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db() -> None:
    """Crea las tablas si no existen. Llamar una vez al inicio del pipeline."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_articles (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url   TEXT NOT NULL UNIQUE,
                source_name  TEXT NOT NULL,
                wp_post_id   INTEGER,
                wp_slug      TEXT,
                seo_keyword  TEXT,
                processed_at DATETIME NOT NULL,
                status       TEXT NOT NULL,
                error_msg    TEXT
            );

            CREATE TABLE IF NOT EXISTS run_log (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at              DATETIME NOT NULL,
                articles_found      INTEGER DEFAULT 0,
                articles_processed  INTEGER DEFAULT 0,
                articles_published  INTEGER DEFAULT 0,
                articles_failed     INTEGER DEFAULT 0
            );
        """)
    logger.debug(f"Base de datos inicializada en: {DB_PATH}")


def is_already_processed(source_url: str) -> bool:
    """Devuelve True si el artículo ya fue procesado (clave de deduplicación)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM processed_articles WHERE source_url = ?",
            (source_url,)
        ).fetchone()
    return row is not None


def mark_as_published(source_url: str, source_name: str, wp_post_id: int, wp_slug: str, seo_keyword: str = "") -> None:
    """Registra publicación exitosa."""
    with get_connection() as conn:
        # Añadir columna seo_keyword si no existe (migración automática)
        try:
            conn.execute("ALTER TABLE processed_articles ADD COLUMN seo_keyword TEXT")
        except Exception:
            pass  # Ya existe

        conn.execute("""
            INSERT INTO processed_articles
                (source_url, source_name, wp_post_id, wp_slug, seo_keyword, processed_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'published')
            ON CONFLICT(source_url) DO UPDATE SET
                wp_post_id   = excluded.wp_post_id,
                wp_slug      = excluded.wp_slug,
                seo_keyword  = excluded.seo_keyword,
                processed_at = excluded.processed_at,
                status       = 'published',
                error_msg    = NULL
        """, (source_url, source_name, wp_post_id, wp_slug, seo_keyword, datetime.now().isoformat()))
    logger.debug(f"Marcado como publicado: {source_url} → WP ID {wp_post_id}")


def mark_as_failed(source_url: str, source_name: str, error_msg: str) -> None:
    """
    Registra fallo. Los artículos fallidos SE REINTENTAN en el próximo run
    porque los fallos suelen ser transitorios (red, rate limit, etc.).
    Para omitir permanentemente, cambiar status a 'skipped' en la BD.
    """
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO processed_articles
                (source_url, source_name, processed_at, status, error_msg)
            VALUES (?, ?, ?, 'failed', ?)
            ON CONFLICT(source_url) DO UPDATE SET
                processed_at = excluded.processed_at,
                status       = 'failed',
                error_msg    = excluded.error_msg
        """, (source_url, source_name, datetime.now().isoformat(), error_msg[:500]))
    logger.debug(f"Marcado como fallido: {source_url}")


def record_run(stats: dict) -> None:
    """Añade una fila al historial de ejecuciones."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO run_log
                (run_at, articles_found, articles_processed, articles_published, articles_failed)
            VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            stats.get("articles_found", 0),
            stats.get("articles_processed", 0),
            stats.get("articles_published", 0),
            stats.get("articles_failed", 0),
        ))
    logger.info(f"Run registrado: {stats}")
