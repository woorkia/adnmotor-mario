import json
import re
import logging
from dataclasses import dataclass
from typing import List, Optional

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS, TEMPERATURE
from fetcher import RawArticle

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Eres un periodista experto en automoción que escribe para adnmotor.com, \
un medio español especializado en coches, motos y motor en general.
Tu estilo es directo, apasionado y bien documentado. Siempre escribes en español de España.
Nunca copias texto literalmente de otras fuentes. Siempre añades valor editorial propio."""


@dataclass
class ProcessedArticle:
    """Artículo procesado por IA, listo para publicar en WordPress."""
    source_url: str
    source_name: str
    article_type: str
    title: str
    slug: str
    meta_description: str
    alternative_titles: List[str]
    seo_keyword: str
    content_html: str


def process_article(article: RawArticle) -> Optional[ProcessedArticle]:
    """
    Envía el artículo a Claude y devuelve ProcessedArticle parseado.
    Devuelve None si el procesamiento falla de forma no recuperable.
    Lanza anthropic.RateLimitError para que el orquestador pueda actuar.
    """
    logger.info(f"Procesando con IA: {article.title[:60]}...")

    raw_response = _call_claude(article)
    if not raw_response:
        return None

    try:
        data = _parse_response(raw_response, article.source_url)
    except ValueError as e:
        logger.error(f"No se pudo parsear respuesta JSON para {article.source_url}: {e}")
        return None

    return ProcessedArticle(
        source_url=article.source_url,
        source_name=article.source_name,
        article_type=data.get("article_type", "noticia"),
        title=data.get("title", article.title),
        slug=data.get("slug", _fallback_slug(article.title)),
        meta_description=data.get("meta_description", "")[:155],
        alternative_titles=data.get("alternative_titles", []),
        seo_keyword=data.get("seo_keyword", ""),
        content_html=data.get("content_html", ""),
    )


def _call_claude(article: RawArticle) -> Optional[str]:
    """Llama a la API de Claude. Devuelve el texto bruto de la respuesta."""
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": _build_prompt(article)}
            ]
        )
        return response.content[0].text
    except anthropic.RateLimitError:
        logger.warning("Rate limit de Claude alcanzado.")
        raise  # El orquestador captura esto para detener el run
    except anthropic.APIError as e:
        logger.error(f"Error de API de Claude: {e}")
        return None


def _build_prompt(article: RawArticle) -> str:
    # Limitar contenido a 3000 chars para no exceder context window innecesariamente
    content_preview = article.content[:3000]
    if len(article.content) > 3000:
        content_preview += "\n[... contenido truncado ...]"

    return f"""Analiza el siguiente artículo de automoción y genera contenido original y optimizado para SEO.

## ARTÍCULO FUENTE
Título original: {article.title}
Fuente: {article.source_name}
URL: {article.source_url}
Contenido:
{content_preview}

## INSTRUCCIONES

### PASO 1: IDENTIFICACIÓN DEL TIPO
Identifica el tipo de artículo:
- noticia: nuevo lanzamiento, anuncio, declaración oficial
- prueba: test drive, análisis de un vehículo concreto
- comparativa: comparación entre dos o más vehículos
- rumor: información no confirmada, filtración, espía
- guia: consejos, cómo hacer algo, recomendaciones

### PASO 2: REESCRITURA COMPLETA
Reescribe el contenido COMPLETAMENTE en español de España, mejorando calidad y claridad.
Añade valor real: contexto, datos técnicos relevantes, impacto en el mercado, comparaciones útiles.
NO copies frases del original. NO traduzcas literalmente. Escribe desde cero.

### PASO 3: ESTRUCTURA HTML (sin H1 — va aparte)
Genera el artículo completo en HTML semántico:
- Usa H2 para secciones principales (mínimo 3, máximo 6)
- Usa H3 para subsecciones cuando sea necesario
- Párrafos con <p> tags
- Términos clave en <strong>
- Longitud objetivo: 600-900 palabras

Estructura según tipo:
- noticia: Contexto → Detalles clave → Implicaciones → Conclusión
- prueba: Introducción → Diseño → Motor y prestaciones → Tecnología → Precio y conclusión
- comparativa: Presentación → Comparativa por aspectos → Veredicto
- rumor: Qué se sabe → Fuentes → Análisis de credibilidad → Qué esperar
- guia: Introducción al problema → Pasos/consejos → Errores comunes → Resumen

### PASO 4: SEO
- Detecta la keyword principal automáticamente
- Inclúyela en el primer párrafo y en al menos un H2
- Densidad natural, nunca forzada

### PASO 5: ESTILO
- Tono profesional pero cercano
- Lenguaje natural, sin estilo robótico
- Pequeñas frases de análisis y opinión experta

### FORMATO DE RESPUESTA
Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura exacta (sin markdown, sin texto extra):

{{
  "article_type": "noticia|prueba|comparativa|rumor|guia",
  "title": "Título H1 optimizado para SEO (máx 65 caracteres)",
  "slug": "url-slug-seo-en-minusculas-con-guiones",
  "meta_description": "Meta descripción persuasiva máx 155 caracteres con keyword principal",
  "alternative_titles": [
    "Título alternativo 1",
    "Título alternativo 2",
    "Título alternativo 3"
  ],
  "seo_keyword": "keyword principal detectada",
  "content_html": "<h2>Primera sección</h2><p>Contenido...</p>"
}}"""


def _parse_response(raw_text: str, source_url: str) -> dict:
    """
    Extracción robusta de JSON de la respuesta de Claude.
    Intenta json.loads() directo; si falla, extrae con regex.
    """
    text = raw_text.strip()

    # Intento 1: JSON directo
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Intento 2: Claude a veces envuelve en bloques markdown ```json ... ```
    md_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if md_match:
        try:
            return json.loads(md_match.group(1))
        except json.JSONDecodeError:
            pass

    # Intento 3: Extraer primer objeto JSON del texto
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No se encontró JSON válido en la respuesta para {source_url}")


def _fallback_slug(title: str) -> str:
    """Genera un slug básico a partir del título si Claude no devuelve uno."""
    slug = title.lower()
    slug = re.sub(r"[áàäâ]", "a", slug)
    slug = re.sub(r"[éèëê]", "e", slug)
    slug = re.sub(r"[íìïî]", "i", slug)
    slug = re.sub(r"[óòöô]", "o", slug)
    slug = re.sub(r"[úùüû]", "u", slug)
    slug = re.sub(r"[ñ]", "n", slug)
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug.strip())
    return slug[:70]
