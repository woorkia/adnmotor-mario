import os
from dotenv import load_dotenv

load_dotenv(override=True)

# --- IA ---
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
HIGGSFIELD_API_KEY = os.getenv("HIGGSFIELD_API_KEY", "")

# --- Imágenes ---
# "pexels"     → fotos de stock gratis (requiere PEXELS_API_KEY)
# "higgsfield" → regeneración con IA    (requiere HIGGSFIELD_API_KEY con créditos)
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "pexels")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
TEMPERATURE = 0.7

# --- WordPress ---
WP_URL = os.getenv("WP_URL", "https://adnmotor.com")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_PASSWORD = os.getenv("WP_PASSWORD")
WP_API_BASE = f"{WP_URL}/wp-json/wp/v2"
WP_AUTH_TIMEOUT = 10
WP_PUBLISH_TIMEOUT = 30

# --- Comportamiento del pipeline ---
MAX_ARTICLES_PER_RUN = 5       # Cap por ejecución (controla costes de API)
MIN_ARTICLE_CONTENT_LENGTH = 300  # Chars mínimos; artículos más cortos se descartan
REQUEST_DELAY_SECONDS = 2      # Delay entre llamadas (scraping educado y entre API calls)

# --- Fuentes RSS ---
# Añadir o quitar fuentes aquí sin tocar el código
RSS_FEEDS = [
    {
        "name": "Motor.es",
        "url": "https://www.motor.es/feed/",
        "category_hint": "noticia",
    },
    {
        "name": "Autopista",
        "url": "https://www.autopista.es/rss.xml",
        "category_hint": "noticia",
    },
    # Km77 no ofrece feed RSS público — añadir aquí más fuentes si se encuentran
    # Ejemplos de fuentes alternativas a explorar:
    # {"name": "Motorpasion", "url": "https://www.motorpasion.com/rss", "category_hint": "noticia"},
    # {"name": "Autofacil",   "url": "https://www.autofacil.es/rss",   "category_hint": "noticia"},
]

# --- Mapeo de tipo de artículo a categoría de WordPress ---
# IMPORTANTE: Actualizar estos IDs consultando:
#   GET https://adnmotor.com/wp-json/wp/v2/categories
# Los valores actuales son placeholders.
CATEGORY_MAP = {
    "noticia":     19,  # NOTICIAS
    "prueba":      22,  # COMPARATIVAS Y GUÍAS
    "comparativa": 22,  # COMPARATIVAS Y GUÍAS
    "rumor":       19,  # NOTICIAS (no hay categoría específica)
    "guia":        22,  # COMPARATIVAS Y GUÍAS
    "default":     19,  # NOTICIAS (fallback)
}

# --- Base de datos ---
# Usar ruta fuera de OneDrive para evitar conflictos de lock durante sync
DB_PATH = os.path.join(os.path.expanduser("~"), "AppData", "Local", "adnmotor", "adnmotor.db")

# --- Logging ---
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "adnmotor.log")
LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 MB
LOG_BACKUP_COUNT = 3
