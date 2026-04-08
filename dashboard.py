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
from functools import wraps
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, flash
from requests.auth import HTTPBasicAuth
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

import config
import database

app = Flask(__name__)
# Usar clave aleatoria si no hay variable de entorno (vuelve a pedir login al reiniciar el servidor)
# Recomendado: configurar SECRET_KEY en Render para sesiones persistentes.
app.secret_key = os.environ.get("SECRET_KEY", "adnmotor-secret-2024-xK9#mP2$")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

TASK_NAME = "ADNMotor Pipeline"


# ─── AUTH ────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

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


# ─── SCHEDULER (APScheduler) ────────────────────────────────────────────────

scheduler = BackgroundScheduler()
SCHEDULER_CONFIG_PATH = os.path.join(os.path.dirname(config.DB_PATH), "scheduler_config.json")

def load_scheduler_config():
    if os.path.exists(SCHEDULER_CONFIG_PATH):
        try:
            with open(SCHEDULER_CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"enabled": False, "interval_hours": 4}

def save_scheduler_config(conf):
    with open(SCHEDULER_CONFIG_PATH, "w") as f:
        json.dump(conf, f)

def pipeline_job():
    try:
        subprocess.run(
            [sys.executable, "main.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            timeout=600
        )
    except Exception as e:
        print(f"Error in scheduled pipeline: {e}")

def apply_scheduler_config():
    conf = load_scheduler_config()
    job_id = "adnmotor_pipeline"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    
    if conf.get("enabled", False):
        hours = conf.get("interval_hours", 4)
        scheduler.add_job(
            func=pipeline_job,
            trigger=IntervalTrigger(hours=hours),
            id=job_id,
            name=TASK_NAME,
            replace_existing=True
        )

# Start scheduler initially
apply_scheduler_config()
scheduler.start()

# Asegurar que la BD está inicializada al arrancar el servidor (importante para Gunicorn)
try:
    database.initialize_db()
except Exception as e:
    print(f"Error initializing database: {e}")


def get_scheduler_status() -> dict:
    """Consulta el estado del scheduler basado en APScheduler."""
    conf = load_scheduler_config()
    job = scheduler.get_job("adnmotor_pipeline")
    
    status = {
        "exists": True,
        "enabled": conf.get("enabled", False),
        "next_run": "—",
        "last_run": "—",
        "interval": conf.get("interval_hours", 4)
    }
    
    if job and job.next_run_time:
        status["next_run"] = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
        
    try:
        with _db_conn() as conn:
            row = conn.execute("SELECT run_at FROM run_log ORDER BY run_at DESC LIMIT 1").fetchone()
            status["last_run"] = row[0] if row else "—"
    except Exception:
        pass
        
    return status


def create_scheduler_task(interval_hours: int = 4) -> dict:
    """Crea o recrea la tarea programada con el intervalo dado."""
    try:
        conf = load_scheduler_config()
        conf["interval_hours"] = interval_hours
        conf["enabled"] = True
        save_scheduler_config(conf)
        apply_scheduler_config()
        return {"ok": True, "output": f"Configurado para ejecutarse cada {interval_hours}h usando APScheduler."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def toggle_scheduler_task(enable: bool) -> dict:
    """Habilita o deshabilita la tarea programada."""
    try:
        conf = load_scheduler_config()
        conf["enabled"] = enable
        save_scheduler_config(conf)
        apply_scheduler_config()
        return {"ok": True, "output": "Activado" if enable else "Desactivado"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            # Asegurar BD lista antes de verificar (por si el init falló al arrancar)
            database.initialize_db()
            if database.verify_password(username, password):
                session["logged_in"] = True
                session["username"] = username
                return redirect(url_for("index"))
            else:
                flash("Usuario o contraseña incorrectos")
        except Exception as e:
            flash(f"Error interno: {e}")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    try:
        # Ya no inicializamos aquí por rendimiento, se hace al arrancar el proceso
        return render_template(
            "index.html",
            stats      = get_stats(),
            runs       = get_runs(),
            drafts     = get_wp_drafts(),
            chart_data = get_chart_data(),
            log_lines  = get_log_lines(),
        )
    except Exception as e:
        import traceback
        # Retornamos el error como texto para depuración fácil en el navegador
        err_trace = traceback.format_exc()
        return f"<h1>Error Interno (500)</h1><p>{e}</p><pre>{err_trace}</pre>", 500


@app.route("/api/stats")
@login_required
def api_stats():
    return jsonify({"stats": get_stats(), "chart_data": get_chart_data()})


@app.route("/api/logs")
@login_required
def api_logs():
    return jsonify({"lines": get_log_lines()})


@app.route("/api/run", methods=["POST"])
@login_required
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
@login_required
def api_scheduler():
    return jsonify(get_scheduler_status())


@app.route("/api/scheduler/create", methods=["POST"])
@login_required
def api_scheduler_create():
    data = request.get_json() or {}
    interval = int(data.get("interval", 4))
    result = create_scheduler_task(interval)
    return jsonify(result)


@app.route("/api/scheduler/toggle", methods=["POST"])
@login_required
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
