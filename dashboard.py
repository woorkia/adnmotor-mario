"""
ADNMotor Dashboard
==================
Panel web para gestionar y monitorizar el pipeline de automatización.

Uso:
    python dashboard.py

Abre en el navegador: http://localhost:5000
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timedelta

import requests
from flask import Flask, jsonify, render_template, request
from requests.auth import HTTPBasicAuth

import config
import database

app = Flask(__name__)

TASK_NAME = "ADNMotor Pipeline"

# ─── HELPERS ────────────────────────────────────────────────────────────────


def _db_conn():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    return sqlite3.connect(config.DB_PATH)


def _count(conn, sql, params=()):
    """Ejecuta una query COUNT y devuelve int puro."""
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def _rows_as_dicts(conn, sql, params=()):
    """Devuelve lista de dicts a partir de un SELECT."""
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_stats() -> dict:
    """Calcula estadísticas desde la base de datos local."""
    try:
        with _db_conn() as conn:
            today_str = datetime.now().strftime("%Y-%m-%d")
            week_ago  = (datetime.now() - timedelta(days=7)).isoformat()

            today     = _count(conn, "SELECT COUNT(*) FROM processed_articles WHERE status='published' AND processed_at LIKE ?", (f"{today_str}%",))
            week      = _count(conn, "SELECT COUNT(*) FROM processed_articles WHERE status='published' AND processed_at >= ?", (week_ago,))
            total     = _count(conn, "SELECT COUNT(*) FROM processed_articles WHERE status='published'")
            total_all = _count(conn, "SELECT COUNT(*) FROM processed_articles")

            success_rate = round((total / total_all * 100) if total_all > 0 else 0, 1)

        return {"today": today, "week": week, "total": total, "success_rate": success_rate}
    except Exception:
        return {"today": 0, "week": 0, "total": 0, "success_rate": 0}


def get_runs(limit: int = 10) -> list:
    """Devuelve las últimas ejecuciones del pipeline."""
    try:
        with _db_conn() as conn:
            return _rows_as_dicts(conn, "SELECT * FROM run_log ORDER BY run_at DESC LIMIT ?", (limit,))
    except Exception:
        return []


def get_chart_data() -> dict:
    """Datos para el gráfico de barras: artículos publicados por día (últimos 7 días)."""
    try:
        labels, values = [], []
        with _db_conn() as conn:
            for i in range(6, -1, -1):
                day     = datetime.now() - timedelta(days=i)
                day_str = day.strftime("%Y-%m-%d")
                labels.append(day.strftime("%d/%m"))
                values.append(_count(conn, "SELECT COUNT(*) FROM processed_articles WHERE status='published' AND processed_at LIKE ?", (f"{day_str}%",)))
        return {"labels": labels, "data": values}
    except Exception:
        return {"labels": [], "data": []}


def get_wp_drafts(limit: int = 20) -> list:
    """
    Obtiene borradores de WordPress via REST API y los enriquece con datos
    de la BD local (keyword SEO, tipo de artículo).
    """
    drafts = []
    try:
        # 1. Traer borradores de WP
        res = requests.get(
            f"{config.WP_API_BASE}/posts",
            auth=HTTPBasicAuth(config.WP_USERNAME, config.WP_PASSWORD),
            params={"status": "draft", "per_page": limit, "orderby": "date", "order": "desc"},
            timeout=10,
            headers={"Accept": "application/json"},
        )
        if res.status_code != 200:
            return []

        wp_posts = res.json()

        # 2. Enriquecer con datos de la BD local
        with _db_conn() as conn:
            for post in wp_posts:
                post_id  = post.get("id")
                title    = post.get("title", {}).get("rendered", "Sin título")
                wp_link  = post.get("link", "#")
                date     = post.get("date", "")

                # Limpiar título HTML
                title = re.sub(r"<[^>]+>", "", title)

                # Buscar datos locales por wp_post_id
                local_rows = _rows_as_dicts(
                    conn,
                    "SELECT * FROM processed_articles WHERE wp_post_id = ?",
                    (post_id,)
                )
                local = local_rows[0] if local_rows else {}

                # Keyword SEO y fuente desde BD local (más fiable que meta WP)
                seo_keyword = local.get("seo_keyword", "") or ""
                source_url  = local.get("source_url", "") or ""
                source_name = local.get("source_name", "") or ""

                drafts.append({
                    "wp_post_id":   post_id,
                    "title":        title,
                    "article_type": local.get("status", "noticia"),
                    "seo_keyword":  seo_keyword,
                    "source_url":   source_url,
                    "source_name":  source_name,
                    "date":         date,
                    "wp_link":      wp_link,
                })
    except Exception:
        pass

    return drafts


def get_log_lines(n: int = 50) -> list:
    """Lee las últimas N líneas del log y devuelve lista de strings."""
    log_path = config.LOG_FILE
    if not os.path.exists(log_path):
        return ["— Log no disponible aún. Ejecuta el pipeline primero."]
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-n:] if l.strip()]
    except Exception as e:
        return [f"— Error leyendo log: {e}"]


# ─── SCHEDULER ──────────────────────────────────────────────────────────────


def get_scheduler_status() -> dict:
    """Consulta el estado de la tarea en Windows Task Scheduler."""
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {"exists": False, "enabled": False, "next_run": "—", "last_run": "—", "interval": None}

        output = result.stdout
        status = {"exists": True, "next_run": "—", "last_run": "—", "interval": None}
        status["enabled"] = not any(x in output for x in ["Disabled", "Deshabilitada", "Deshabilitado"])

        for line in output.splitlines():
            low = line.lower()
            if "next run time" in low or "próxima hora" in low or "proxima hora" in low:
                val = line.split(":", 1)[1].strip() if ":" in line else "—"
                status["next_run"] = val if val and val != "N/A" else "—"
            if "last run time" in low or "última hora" in low or "ultima hora" in low:
                val = line.split(":", 1)[1].strip() if ":" in line else "—"
                status["last_run"] = val if val and val != "N/A" else "—"
            if "schedule type" in low or "tipo de programación" in low or "tipo de programacion" in low:
                status["schedule_type"] = line.split(":", 1)[1].strip() if ":" in line else "—"

        return status
    except Exception as e:
        return {"exists": False, "enabled": False, "next_run": "—", "last_run": "—", "error": str(e)}


def create_scheduler_task(interval_hours: int = 4) -> dict:
    """Crea o recrea la tarea programada con el intervalo dado."""
    try:
        python_exe = sys.executable
        script_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"))
        cmd = [
            "schtasks", "/Create",
            "/TN", TASK_NAME,
            "/TR", f'"{python_exe}" "{script_path}"',
            "/SC", "HOURLY",
            "/MO", str(interval_hours),
            "/ST", "09:00",
            "/F",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return {"ok": result.returncode == 0, "output": (result.stdout or result.stderr).strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def toggle_scheduler_task(enable: bool) -> dict:
    """Habilita o deshabilita la tarea programada."""
    try:
        action = "/Enable" if enable else "/Disable"
        result = subprocess.run(
            ["schtasks", action, "/TN", TASK_NAME],
            capture_output=True, text=True, timeout=10
        )
        return {"ok": result.returncode == 0, "output": (result.stdout or result.stderr).strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    database.initialize_db()
    return render_template(
        "index.html",
        stats      = get_stats(),
        runs       = get_runs(),
        drafts     = get_wp_drafts(),
        chart_data = get_chart_data(),
        log_lines  = get_log_lines(),
    )


@app.route("/api/stats")
def api_stats():
    return jsonify({"stats": get_stats(), "chart_data": get_chart_data()})


@app.route("/api/logs")
def api_logs():
    return jsonify({"lines": get_log_lines()})


@app.route("/api/run", methods=["POST"])
def api_run():
    """
    Lanza main.py en un proceso separado para no bloquear el dashboard.
    Devuelve inmediatamente; el pipeline corre en background.
    """
    def run_pipeline():
        try:
            subprocess.run(
                [sys.executable, "main.py"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                timeout=600,
            )
        except Exception:
            pass

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": "Pipeline iniciado en segundo plano"})


@app.route("/api/scheduler")
def api_scheduler():
    return jsonify(get_scheduler_status())


@app.route("/api/scheduler/create", methods=["POST"])
def api_scheduler_create():
    data = request.get_json() or {}
    interval = int(data.get("interval", 4))
    result = create_scheduler_task(interval)
    return jsonify(result)


@app.route("/api/scheduler/toggle", methods=["POST"])
def api_scheduler_toggle():
    data = request.get_json() or {}
    enable = bool(data.get("enable", True))
    result = toggle_scheduler_task(enable)
    return jsonify(result)


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    database.initialize_db()
    print("\n" + "=" * 50)
    print("  ADNMotor Dashboard")
    print("  http://localhost:5000")
    print("=" * 50 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
