"""
ADNMotor Content Automation Pipeline
=====================================
Flujo: Fetch RSS → Deduplicar → Procesar con Claude → Publicar borrador en WordPress

Uso:
    python main.py

Programación (Windows Task Scheduler):
    Programa:    python.exe
    Argumentos:  main.py
    Directorio:  <ruta de este proyecto>
    Frecuencia:  Cada 4 horas (máx 30 artículos/día con MAX_ARTICLES_PER_RUN=5)
"""

import logging
import logging.handlers
import os
import sys
import time

import anthropic

import config
import database
import fetcher
import image_processor
import processor
import publisher


def setup_logging() -> None:
    """Configura rotating file handler + salida por consola."""
    os.makedirs(config.LOG_DIR, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Handler de archivo con rotación
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)

    # Handler de consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def validate_config() -> bool:
    """Comprueba que las variables de entorno críticas están configuradas."""
    errors = []
    if not config.ANTHROPIC_API_KEY or "PON_AQUI" in config.ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY no configurada en .env")
    if not config.WP_USERNAME:
        errors.append("WP_USERNAME no configurado en .env")
    if not config.WP_PASSWORD or "PON_AQUI" in config.WP_PASSWORD:
        errors.append("WP_PASSWORD (Application Password) no configurado en .env")
    if errors:
        for err in errors:
            logging.getLogger(__name__).critical(f"Configuración incompleta: {err}")
        return False
    return True


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("ADNMotor Pipeline INICIO")
    logger.info("=" * 60)

    stats = {
        "articles_found": 0,
        "articles_processed": 0,
        "articles_published": 0,
        "articles_failed": 0,
    }

    # 1. Validar configuración
    if not validate_config():
        logger.critical("Corrige el archivo .env antes de continuar.")
        sys.exit(1)

    # 2. Inicializar base de datos
    database.initialize_db()
    logger.info(f"Base de datos lista: {config.DB_PATH}")

    # 3. Verificar conexión WordPress (fail fast)
    logger.info("Verificando conexión con WordPress...")
    if not publisher.verify_connection():
        logger.critical("No se puede conectar a WordPress. Abortando.")
        sys.exit(1)

    # 4. Captar artículos de todos los feeds RSS
    logger.info("Captando artículos de feeds RSS...")
    raw_articles = fetcher.fetch_all_feeds()
    stats["articles_found"] = len(raw_articles)
    logger.info(f"Total artículos captados: {len(raw_articles)}")

    # 5. Filtrar los ya procesados (deduplicación)
    new_articles = [
        a for a in raw_articles
        if not database.is_already_processed(a.source_url)
    ]
    logger.info(f"Artículos nuevos (no procesados aún): {len(new_articles)}")

    if not new_articles:
        logger.info("No hay artículos nuevos en esta ejecución.")
        database.record_run(stats)
        return

    # 6. Limitar por run (control de costes)
    articles_to_process = new_articles[:config.MAX_ARTICLES_PER_RUN]
    logger.info(f"Procesando {len(articles_to_process)} artículos (límite: {config.MAX_ARTICLES_PER_RUN})")

    # 7. Procesar y publicar
    for i, article in enumerate(articles_to_process, 1):
        logger.info(f"[{i}/{len(articles_to_process)}] {article.title[:70]}")

        # 7a. Procesamiento con IA
        processed = None
        try:
            processed = processor.process_article(article)
        except anthropic.RateLimitError:
            logger.warning("Rate limit de Claude alcanzado. Deteniendo run actual.")
            logger.info("El próximo run continuará con los artículos pendientes.")
            break
        except Exception as e:
            logger.error(f"Error en procesamiento IA: {e}")
            database.mark_as_failed(article.source_url, article.source_name, str(e))
            stats["articles_failed"] += 1
            continue

        if processed is None:
            logger.warning(f"Procesamiento devolvió None para: {article.source_url}")
            database.mark_as_failed(
                article.source_url, article.source_name,
                "processor.process_article devolvió None"
            )
            stats["articles_failed"] += 1
            continue

        # 7b. Obtener imagen (Pexels o Higgsfield) y subir a WP Media
        featured_media_id = None
        has_image_provider = bool(config.PEXELS_API_KEY or config.HIGGSFIELD_API_KEY)
        if has_image_provider:
            logger.info(f"Procesando imagen con Higgsfield...")
            featured_media_id = image_processor.process_article_image(
                source_image_url=article.image_url,
                article_title=processed.title,
                slug=processed.slug,
                seo_keyword=processed.seo_keyword,
            )
            if featured_media_id:
                logger.info(f"Imagen destacada lista: WP Media ID={featured_media_id}")
            else:
                logger.info("Imagen no disponible — el artículo se publicará sin imagen destacada")

        # 7c. Publicar en WordPress como borrador
        try:
            wp_post_id = publisher.publish_draft(processed, featured_media_id=featured_media_id)
            database.mark_as_published(
                article.source_url,
                article.source_name,
                wp_post_id,
                processed.slug,
                processed.seo_keyword,
            )
            stats["articles_processed"] += 1
            stats["articles_published"] += 1
            logger.info(f"Borrador publicado: WP ID={wp_post_id} | Slug={processed.slug}")
        except publisher.PublishError as e:
            logger.error(f"Error al publicar en WordPress: {e}")
            database.mark_as_failed(article.source_url, article.source_name, str(e))
            stats["articles_failed"] += 1
        except Exception as e:
            logger.error(f"Error inesperado al publicar: {e}")
            database.mark_as_failed(article.source_url, article.source_name, str(e))
            stats["articles_failed"] += 1

        # Delay entre artículos (respeto a APIs)
        if i < len(articles_to_process):
            time.sleep(config.REQUEST_DELAY_SECONDS)

    # 8. Registrar estadísticas del run
    database.record_run(stats)
    logger.info("=" * 60)
    logger.info(
        f"Pipeline COMPLETADO | "
        f"Captados: {stats['articles_found']} | "
        f"Publicados: {stats['articles_published']} | "
        f"Fallidos: {stats['articles_failed']}"
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
