import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import feedparser
import requests
from bs4 import BeautifulSoup

from config import RSS_FEEDS, MIN_ARTICLE_CONTENT_LENGTH, REQUEST_DELAY_SECONDS

logger = logging.getLogger(__name__)

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


@dataclass
class RawArticle:
    """Contenedor inmutable para un artículo captado antes del procesamiento con IA."""
    source_url: str
    source_name: str
    title: str
    content: str
    published_date: str
    category_hint: str
    image_url: Optional[str] = None


def fetch_all_feeds() -> List[RawArticle]:
    """
    Itera todos los RSS_FEEDS, llama a fetch_feed() para cada uno.
    Aplica delay entre feeds. Los errores en feeds individuales no detienen el pipeline.
    """
    all_articles: List[RawArticle] = []
    seen_urls: set = set()

    for i, feed_config in enumerate(RSS_FEEDS):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

        try:
            articles = fetch_feed(feed_config)
            for article in articles:
                if article.source_url not in seen_urls:
                    seen_urls.add(article.source_url)
                    all_articles.append(article)
            logger.info(f"[{feed_config['name']}] {len(articles)} artículos captados")
        except Exception as e:
            logger.warning(f"[{feed_config['name']}] Error procesando feed: {e}")

    logger.info(f"Total artículos únicos captados de todos los feeds: {len(all_articles)}")
    return all_articles


def fetch_feed(feed_config: dict) -> List[RawArticle]:
    """
    Parsea un único feed RSS. Devuelve lista de RawArticle.
    Nunca lanza excepciones; devuelve [] en caso de fallo.
    Descarga el feed con requests (+ User-Agent) antes de parsear,
    porque algunos sitios bloquean el User-Agent por defecto de feedparser.
    """
    feed_url = feed_config["url"]
    feed_name = feed_config["name"]
    category_hint = feed_config.get("category_hint", "noticia")

    try:
        response = requests.get(feed_url, headers=SCRAPE_HEADERS, timeout=15)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except Exception as e:
        logger.warning(f"[{feed_name}] No se pudo descargar el feed: {e}")
        return []

    if parsed.bozo and not parsed.entries:
        logger.warning(f"[{feed_name}] Feed no válido o inaccesible: {feed_url}")
        return []

    articles = []
    for entry in parsed.entries:
        try:
            source_url = getattr(entry, "link", None)
            if not source_url:
                continue

            title = getattr(entry, "title", "").strip()
            if not title:
                continue

            content = _extract_content(entry, feed_url)
            if len(content) < MIN_ARTICLE_CONTENT_LENGTH:
                logger.debug(f"[{feed_name}] Artículo demasiado corto ({len(content)} chars), omitido: {title[:50]}")
                continue

            published_date = ""
            if hasattr(entry, "published"):
                published_date = entry.published
            elif hasattr(entry, "updated"):
                published_date = entry.updated

            image_url = _extract_image(entry)

            articles.append(RawArticle(
                source_url=source_url,
                source_name=feed_name,
                title=title,
                content=content,
                published_date=published_date,
                category_hint=category_hint,
                image_url=image_url,
            ))
        except Exception as e:
            logger.debug(f"[{feed_name}] Error procesando entrada: {e}")
            continue

    return articles


def _extract_content(entry: feedparser.FeedParserDict, feed_url: str) -> str:
    """
    Extrae texto del artículo en orden de prioridad:
    1. entry.content[0].value  (HTML completo — mejor)
    2. entry.summary           (resumen parcial — habitual en feeds españoles)
    3. Scraping de la URL      (último recurso)
    """
    raw_html = ""

    # 1. Contenido completo en el feed
    if hasattr(entry, "content") and entry.content:
        raw_html = entry.content[0].get("value", "")

    # 2. Summary
    if not raw_html and hasattr(entry, "summary"):
        raw_html = entry.summary

    # 3. Scraping si lo anterior es insuficiente
    if len(_strip_html(raw_html)) < MIN_ARTICLE_CONTENT_LENGTH:
        source_url = getattr(entry, "link", "")
        if source_url:
            scraped = _fetch_article_body(source_url)
            if len(scraped) > len(_strip_html(raw_html)):
                return scraped

    return _strip_html(raw_html)


def _strip_html(html: str) -> str:
    """Elimina tags HTML y devuelve texto limpio."""
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
        return soup.get_text(separator=" ", strip=True)
    except Exception:
        return html


def _fetch_article_body(url: str) -> str:
    """
    Scraping de último recurso: descarga la página y extrae el cuerpo principal.
    Busca <article>, luego divs con clases comunes, luego el div más grande.
    """
    try:
        response = requests.get(url, headers=SCRAPE_HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        # Eliminar nav, footer, scripts, etc.
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()

        # 1. Buscar <article>
        article_tag = soup.find("article")
        if article_tag:
            return article_tag.get_text(separator=" ", strip=True)

        # 2. Buscar divs con clases comunes de contenido
        for class_name in ["article-body", "post-content", "entry-content", "content-body", "article__body"]:
            div = soup.find("div", class_=class_name)
            if div:
                return div.get_text(separator=" ", strip=True)

        # 3. Div más grande por longitud de texto
        divs = soup.find_all("div")
        if divs:
            best = max(divs, key=lambda d: len(d.get_text()))
            text = best.get_text(separator=" ", strip=True)
            if len(text) >= MIN_ARTICLE_CONTENT_LENGTH:
                return text

    except Exception as e:
        logger.debug(f"Scraping fallido para {url}: {e}")

    return ""


def _extract_image(entry: feedparser.FeedParserDict) -> Optional[str]:
    """Intenta extraer URL de imagen del feed entry."""
    # Enclosures (podcasts y algunos feeds de noticias)
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image/"):
                return enc.get("href")

    # Media content (estándar de Yahoo Media RSS)
    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            if media.get("medium") == "image" or media.get("type", "").startswith("image/"):
                return media.get("url")

    # Media thumbnail
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")

    return None
