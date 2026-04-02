"""
image_processor.py
==================
Obtiene una imagen relevante para el artículo y la sube a WordPress
como imagen destacada del post.

Proveedores disponibles (configurar IMAGE_PROVIDER en config.py):
  - "pexels"     : Busca foto de stock relevante via Pexels API (gratis, 20k/mes)
  - "higgsfield" : Pexels busca imagen por keyword → Higgsfield la regenera con IA

Flujo Pexels:
  seo_keyword → Pexels API → foto relevante → WP Media → featured_media ID

Flujo Higgsfield (imagen 100% original):
  seo_keyword → Pexels API → foto base → Higgsfield IA → imagen regenerada → WP Media
"""

import logging
import os
import time

import requests
from requests.auth import HTTPBasicAuth

import config

logger = logging.getLogger(__name__)


# ─── PEXELS ──────────────────────────────────────────────────────────────────

def _search_pexels(query: str) -> str | None:
    """
    Busca una foto relevante en Pexels y devuelve la URL de descarga.
    Prioriza imágenes landscape (16:9) de alta calidad.
    """
    if not config.PEXELS_API_KEY:
        logger.warning("PEXELS_API_KEY no configurada")
        return None

    try:
        # Búsqueda principal con keyword del artículo
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": config.PEXELS_API_KEY},
            params={
                "query":       query,
                "orientation": "landscape",
                "size":        "large",
                "per_page":    5,
            },
            timeout=10,
        )

        if resp.status_code != 200:
            logger.warning(f"Pexels devolvió {resp.status_code}")
            return None

        photos = resp.json().get("photos", [])

        # Si no hay resultados, buscar genérico de coches
        if not photos:
            resp2 = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": config.PEXELS_API_KEY},
                params={"query": "car automobile", "orientation": "landscape", "per_page": 3},
                timeout=10,
            )
            photos = resp2.json().get("photos", []) if resp2.status_code == 200 else []

        if not photos:
            logger.warning("Pexels no devolvió fotos")
            return None

        # Coger la primera foto — URL de alta calidad (large2x o large)
        photo = photos[0]
        image_url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
        photographer = photo.get("photographer", "")
        logger.info(f"Foto Pexels encontrada — autor: {photographer} | URL: {image_url[:60]}...")
        return image_url

    except Exception as e:
        logger.warning(f"Error en búsqueda Pexels: {e}")
        return None


# ─── HIGGSFIELD ──────────────────────────────────────────────────────────────

def _generate_higgsfield(source_image_url: str, article_title: str, seo_keyword: str = "") -> str | None:
    """
    Descarga la imagen base (Pexels o RSS), la sube a Higgsfield y genera
    una nueva versión fotorrealista única. Requiere créditos en Higgsfield.
    """
    if not config.HIGGSFIELD_API_KEY:
        logger.warning("HIGGSFIELD_API_KEY no configurada")
        return None

    os.environ["HF_KEY"] = config.HIGGSFIELD_API_KEY

    try:
        import higgsfield_client
        from PIL import Image
        from io import BytesIO

        # 1. Descargar imagen base
        logger.info(f"Higgsfield: descargando imagen base...")
        resp = requests.get(source_image_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            logger.warning(f"No se pudo descargar imagen base ({resp.status_code})")
            return None

        # 2. Convertir a PIL Image y subir a Higgsfield
        pil_image = Image.open(BytesIO(resp.content)).convert("RGB")
        logger.info(f"Higgsfield: subiendo imagen ({pil_image.width}x{pil_image.height})...")
        hf_url = higgsfield_client.upload_image(pil_image, format="jpeg")
        logger.info(f"Higgsfield: imagen subida -> {hf_url[:60]}...")

        # 3. Prompt fotorrealista de automoción
        keyword = seo_keyword or article_title
        prompt = (
            f"Professional automotive photography of {article_title}, "
            "well-known real production car, widely documented design, match official manufacturer design, "
            "strictly accurate model representation, no alterations to design, "
            "no redesign, no concept car, no futuristic reinterpretation, "
            "correct body shape, exact proportions, accurate headlights, grille, rims, logo, badges and branding exactly as real model, "
            f"based on news context: {keyword}, "
            "ultra realistic, photorealistic high resolution, commercial car photography, magazine quality, "
            "camera composition: dynamic 3/4 front view or context-appropriate angle, "
            "lens: 50mm or 85mm, realistic perspective, depth of field, sharp focus, "
            "lighting: cinematic natural lighting or realistic studio lighting depending on scene, "
            "accurate reflections on paint, glass and metallic surfaces, "
            "environment: completely new original setting, different from any source image, "
            "but fully coherent with the news (urban street, highway, mountains, desert, city night, etc), "
            "surface interaction: realistic tire contact, shadows, reflections on ground, "
            "materials: highly detailed textures (paint finish, metallic surfaces, glass transparency, rubber tires), "
            "color accuracy: original factory colors only, no random color changes, "
            "no visual errors, no distorted geometry, no incorrect branding, no mixed car parts, "
            "high detail, hyperrealism, premium automotive advertisement style"
        )

        # 4. Regenerar con IA
        logger.info(f"Higgsfield: regenerando imagen con IA...")
        result = higgsfield_client.subscribe(
            "bytedance/seedream/v4/edit",
            arguments={
                "image_urls":   [hf_url],
                "prompt":       prompt,
                "resolution":   "2K",
                "aspect_ratio": "16:9",
            },
        )

        if result and result.get("images"):
            new_url = result["images"][0]["url"]
            logger.info(f"Higgsfield OK: imagen regenerada -> {new_url[:60]}...")
            return new_url

        logger.warning(f"Higgsfield no devolvio imagenes: {result}")
        return None

    except Exception as e:
        logger.warning(f"Error Higgsfield: {e}")
        return None


# ─── OBTENER IMAGEN (selector de proveedor) ───────────────────────────────────

def regenerate_image(source_image_url: str, article_title: str, seo_keyword: str = "") -> str | None:
    """
    Obtiene una imagen para el artículo según el proveedor configurado.
    Devuelve URL de la imagen lista para subir a WordPress, o None si falla.
    """
    provider = getattr(config, "IMAGE_PROVIDER", "pexels").lower()
    query    = seo_keyword or article_title

    if provider == "pexels":
        return _search_pexels(query)
    elif provider == "higgsfield":
        return _generate_higgsfield(source_image_url, article_title, seo_keyword)
    else:
        logger.warning(f"Proveedor de imagen desconocido: {provider}")
        return None


# ─── WORDPRESS MEDIA ─────────────────────────────────────────────────────────

def upload_image_to_wp(image_url: str, filename: str, alt_text: str = "") -> int | None:
    """
    Descarga la imagen desde image_url y la sube a la biblioteca de medios
    de WordPress via REST API.

    Devuelve el ID del media en WordPress, o None si falla.
    """
    if not image_url:
        return None

    try:
        # 1. Descargar la imagen regenerada
        logger.info(f"Descargando imagen regenerada para subir a WP...")
        resp = requests.get(image_url, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"No se pudo descargar imagen regenerada ({resp.status_code})")
            return None

        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
        ext_map = {
            "image/jpeg": "jpg",
            "image/png":  "png",
            "image/webp": "webp",
        }
        ext = ext_map.get(content_type, "jpg")
        safe_filename = f"{filename}.{ext}" if not filename.endswith(f".{ext}") else filename

        # 2. Subir a WP Media Library
        logger.info(f"Subiendo imagen a WordPress Media: {safe_filename}")
        upload_resp = requests.post(
            f"{config.WP_API_BASE}/media",
            auth=HTTPBasicAuth(config.WP_USERNAME, config.WP_PASSWORD),
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "Content-Type": content_type,
            },
            data=resp.content,
            timeout=60,
        )

        if upload_resp.status_code in (200, 201):
            media_data = upload_resp.json()
            media_id = media_data.get("id")

            # 3. Actualizar el alt text
            if alt_text and media_id:
                requests.post(
                    f"{config.WP_API_BASE}/media/{media_id}",
                    auth=HTTPBasicAuth(config.WP_USERNAME, config.WP_PASSWORD),
                    json={"alt_text": alt_text},
                    timeout=10,
                )

            logger.info(f"Imagen subida a WP Media — ID: {media_id}")
            return media_id

        logger.warning(f"Error subiendo imagen a WP: {upload_resp.status_code} — {upload_resp.text[:200]}")
        return None

    except Exception as e:
        logger.warning(f"Error subiendo imagen a WordPress: {e}")
        return None


# ─── PIPELINE DE IMAGEN COMPLETO ─────────────────────────────────────────────

def process_article_image(
    source_image_url: str,
    article_title: str,
    slug: str,
    seo_keyword: str = "",
) -> int | None:
    """
    Función principal: regenera la imagen con Higgsfield y la sube a WordPress.
    Devuelve el media_id de WordPress para usarlo como featured_media.

    Si cualquier paso falla, devuelve None (el pipeline continúa sin imagen).
    """
    provider = getattr(config, "IMAGE_PROVIDER", "pexels").lower()
    query = seo_keyword or article_title

    if provider == "higgsfield":
        # Paso 1a: Si no hay imagen de origen en el RSS, buscar en Pexels como base
        base_image_url = source_image_url
        if not base_image_url:
            logger.info("Higgsfield: sin imagen de origen en RSS, buscando base en Pexels...")
            base_image_url = _search_pexels(query)
            if not base_image_url:
                logger.warning("No se encontro imagen base en Pexels — articulo sin imagen")
                return None

        # Paso 1b: Regenerar con Higgsfield
        new_image_url = _generate_higgsfield(base_image_url, article_title, seo_keyword)
        if not new_image_url:
            # Fallback: usar la imagen de Pexels directamente
            logger.info("Higgsfield fallo — usando imagen Pexels como fallback")
            new_image_url = base_image_url
    else:
        # Pexels directo
        new_image_url = _search_pexels(query)

    if not new_image_url:
        return None

    # Pequeña pausa para no saturar
    time.sleep(1)

    # Paso 2: Subir a WordPress Media
    media_id = upload_image_to_wp(
        image_url=new_image_url,
        filename=slug,
        alt_text=seo_keyword or article_title,
    )

    return media_id
