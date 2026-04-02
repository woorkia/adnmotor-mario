import logging
import time
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth

from config import (
    WP_API_BASE, WP_USERNAME, WP_PASSWORD,
    WP_AUTH_TIMEOUT, WP_PUBLISH_TIMEOUT, CATEGORY_MAP
)
from processor import ProcessedArticle

logger = logging.getLogger(__name__)


class PublishError(Exception):
    pass


def _auth() -> HTTPBasicAuth:
    """
    Devuelve objeto de autenticación.
    NOTA: Requiere Application Password de WordPress, no la contraseña de cuenta.
    Generar en: WordPress Admin > Usuarios > Tu perfil > Contraseñas de aplicación.
    """
    return HTTPBasicAuth(WP_USERNAME, WP_PASSWORD)


def verify_connection() -> bool:
    """
    Verifica credenciales de WordPress antes de iniciar el pipeline.
    GET /wp-json/wp/v2/users/me
    Devuelve True si el usuario tiene permisos para crear posts.
    """
    try:
        response = requests.get(
            f"{WP_API_BASE}/users/me",
            auth=_auth(),
            timeout=WP_AUTH_TIMEOUT,
            headers={"Accept": "application/json"}
        )
        if response.status_code == 200:
            user_data = response.json()
            capabilities = user_data.get("capabilities", {})
            can_publish = capabilities.get("publish_posts", False) or \
                          capabilities.get("edit_posts", False) or \
                          user_data.get("roles", [])
            logger.info(f"WordPress conectado. Usuario: {user_data.get('name')} | Roles: {user_data.get('roles', [])}")
            return True
        elif response.status_code == 401:
            logger.critical(
                "WordPress devolvió 401. Verifica el Application Password en:\n"
                "WP Admin > Usuarios > Tu perfil > Contraseñas de aplicación"
            )
            return False
        else:
            logger.error(f"WordPress devolvió {response.status_code}: {response.text[:200]}")
            return False
    except requests.RequestException as e:
        logger.critical(f"No se puede conectar a WordPress: {e}")
        return False


def get_category_id(article_type: str) -> int:
    """Devuelve el ID de categoría de WordPress para el tipo de artículo."""
    return CATEGORY_MAP.get(article_type, CATEGORY_MAP["default"])


def publish_draft(article: ProcessedArticle, featured_media_id: Optional[int] = None) -> int:
    """
    Crea un post borrador en WordPress via REST API.
    Devuelve el ID del nuevo post.
    Lanza PublishError en caso de fallo.
    """
    category_id = get_category_id(article.article_type)

    payload = {
        "title":      article.title,
        "content":    article.content_html,
        "status":     "draft",
        "slug":       article.slug,
        "categories": [category_id],
        "excerpt":    article.meta_description,
        # Meta SEO para RankMath
        "meta": {
            "rank_math_description":   article.meta_description,
            "rank_math_focus_keyword": article.seo_keyword,
        },
    }

    # Imagen destacada si se generó con Higgsfield
    if featured_media_id:
        payload["featured_media"] = featured_media_id

    response = _post_with_retry(f"{WP_API_BASE}/posts", payload)

    if response.status_code == 201:
        post_data = response.json()
        post_id = post_data.get("id")
        post_link = post_data.get("link", "")
        logger.info(f"Borrador creado: ID={post_id} | Tipo={article.article_type} | {post_link}")
        return post_id
    else:
        raise PublishError(
            f"WP API devolvió {response.status_code}: {response.text[:300]}"
        )


def _post_with_retry(url: str, payload: dict, retries: int = 1) -> requests.Response:
    """
    POST a la API de WordPress con un reintento en caso de error 429 o 5xx.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept":       "application/json",
        "User-Agent":   "ADNMotor-AutoPipeline/1.0",
    }

    for attempt in range(retries + 1):
        try:
            response = requests.post(
                url,
                json=payload,
                auth=_auth(),
                timeout=WP_PUBLISH_TIMEOUT,
                headers=headers,
            )

            if response.status_code == 429:
                if attempt < retries:
                    logger.warning("WP rate limit (429). Esperando 30s antes de reintentar...")
                    time.sleep(30)
                    continue
                else:
                    return response

            if response.status_code >= 500 and attempt < retries:
                logger.warning(f"WP error {response.status_code}. Reintentando en 10s...")
                time.sleep(10)
                continue

            return response

        except requests.Timeout:
            if attempt < retries:
                logger.warning("Timeout en WP. Reintentando...")
                time.sleep(5)
                continue
            raise PublishError("Timeout persistente al publicar en WordPress")

        except requests.RequestException as e:
            raise PublishError(f"Error de red al publicar: {e}")

    # No debería llegar aquí
    raise PublishError("Todos los intentos de publicación fallaron")


def get_wp_categories() -> dict:
    """
    Utilidad: descarga todas las categorías de WordPress y las imprime.
    Úsala para actualizar CATEGORY_MAP en config.py.
    Ejecutar una vez: python -c "from publisher import get_wp_categories; get_wp_categories()"
    """
    try:
        response = requests.get(
            f"{WP_API_BASE}/categories",
            auth=_auth(),
            timeout=WP_AUTH_TIMEOUT,
            params={"per_page": 100},
        )
        if response.status_code == 200:
            cats = response.json()
            result = {cat["slug"]: cat["id"] for cat in cats}
            logger.info("Categorías de WordPress:")
            for slug, cat_id in result.items():
                logger.info(f"  {cat_id}: {slug}")
            return result
        else:
            logger.error(f"No se pudieron obtener categorías: {response.status_code}")
            return {}
    except Exception as e:
        logger.error(f"Error obteniendo categorías: {e}")
        return {}
