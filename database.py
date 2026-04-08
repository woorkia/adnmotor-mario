import sqlite3
import logging
import os
import bcrypt
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

            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT UNIQUE NOT NULL,
                password   TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS rss_feeds (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                url           TEXT NOT NULL UNIQUE,
                category_hint TEXT DEFAULT 'noticia',
                enabled       INTEGER DEFAULT 1,
                created_at    TEXT DEFAULT (datetime('now'))
            );
        """)

    # Asegurar que el usuario correcto existe
    default_user = "adnmotor.com@gmail.com"
    default_pass = os.environ.get("ADMIN_PASSWORD", "@MarioAdn99.")
    with get_connection() as conn:
        # Limpiar usuario 'admin' genérico si quedó de versión anterior
        conn.execute("DELETE FROM users WHERE username = 'admin'")
        # Crear usuario si no existe
        exists = conn.execute(
            "SELECT COUNT(*) FROM users WHERE username = ?", (default_user,)
        ).fetchone()[0]
        if not exists:
            pw_hash = bcrypt.hashpw(default_pass.encode(), bcrypt.gensalt()).decode()
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (default_user, pw_hash)
            )
            logger.info(f"Usuario creado: {default_user}")

    # Seed fuentes RSS por defecto si la tabla está vacía
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM rss_feeds").fetchone()[0]
        if count == 0:
            default_feeds = [
                ("Motor.es",  "https://www.motor.es/feed/",      "noticia"),
                ("Autopista", "https://www.autopista.es/rss.xml", "noticia"),
            ]
            conn.executemany(
                "INSERT OR IGNORE INTO rss_feeds (name, url, category_hint) VALUES (?, ?, ?)",
                default_feeds
            )
            logger.info("Fuentes RSS por defecto creadas")

    logger.debug(f"Base de datos inicializada en: {DB_PATH}")


def get_user(username: str) -> dict | None:
    """Devuelve el usuario por username, o None si no existe."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    return dict(row) if row else None


def verify_password(username: str, password: str) -> bool:
    """Verifica username y contraseña con bcrypt. Devuelve True si son válidos."""
    user = get_user(username)
    if not user:
        return False
    return bcrypt.checkpw(password.encode(), user["password"].encode())


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


# ─── RSS FEEDS CRUD ──────────────────────────────────────────────────────────

def get_feeds() -> list:
    """Devuelve todos los feeds RSS (solo los activos para el pipeline)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM rss_feeds ORDER BY id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_active_feeds() -> list:
    """Devuelve solo los feeds activos (enabled=1) para el pipeline."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM rss_feeds WHERE enabled=1 ORDER BY id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def add_feed(name: str, url: str, category_hint: str = "noticia") -> int:
    """Añade una nueva fuente RSS. Devuelve el id creado."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO rss_feeds (name, url, category_hint) VALUES (?, ?, ?)",
            (name.strip(), url.strip(), category_hint)
        )
    logger.info(f"Feed añadido: {name} → {url}")
    return cur.lastrowid


def delete_feed(feed_id: int) -> None:
    """Elimina una fuente RSS por id."""
    with get_connection() as conn:
        conn.execute("DELETE FROM rss_feeds WHERE id = ?", (feed_id,))
    logger.info(f"Feed eliminado: id={feed_id}")


def toggle_feed(feed_id: int, enabled: bool) -> None:
    """Activa o desactiva una fuente RSS."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE rss_feeds SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, feed_id)
        )
    logger.info(f"Feed id={feed_id} → {'activo' if enabled else 'desactivado'}")
