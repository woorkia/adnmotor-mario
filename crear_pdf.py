"""
Genera Memoria_Desarrollo_ADNMotor.pdf con diseño premium usando ReportLab.
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.platypus.flowables import Flowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Colores ──────────────────────────────────────────────────────────────────
AZUL_OSCURO  = colors.HexColor("#1B3A6B")
AZUL_WOORKIA = colors.HexColor("#2563EB")
AZUL_CLARO   = colors.HexColor("#60A5FA")
GRIS_FONDO   = colors.HexColor("#F8FAFC")
GRIS_TEXTO   = colors.HexColor("#374151")
GRIS_MEDIO   = colors.HexColor("#9CA3AF")
GRIS_LINEA   = colors.HexColor("#E5E7EB")
BLANCO       = colors.white
VERDE        = colors.HexColor("#16A34A")
NARANJA      = colors.HexColor("#D97706")

W, H = A4  # 595.28 x 841.89 pts

# ── Logo Woorkia como Flowable ────────────────────────────────────────────────
class LogoWoorkia(Flowable):
    def __init__(self, width=180, height=40, color_w=BLANCO, color_accent=AZUL_CLARO):
        super().__init__()
        self.width = width
        self.height = height
        self.color_w = color_w
        self.color_accent = color_accent

    def draw(self):
        c = self.canv
        x, y = 0, 0
        h = self.height
        fs = h * 0.72

        c.saveState()
        # "W" gris/blanco
        c.setFont("Helvetica-Bold", fs)
        c.setFillColor(self.color_w)
        c.drawString(x, y + h*0.1, "W")
        x_after_w = c.stringWidth("W", "Helvetica-Bold", fs)

        # infinito (∞) en acento
        c.setFillColor(self.color_accent)
        inf_w = c.stringWidth("oo", "Helvetica-Bold", fs)
        # dibujar símbolo infinito manual con dos círculos
        cx1 = x + x_after_w + inf_w*0.22
        cx2 = x + x_after_w + inf_w*0.78
        cy  = y + h * 0.45
        r   = inf_w * 0.22
        c.setLineWidth(fs * 0.13)
        c.setStrokeColor(self.color_accent)
        c.circle(cx1, cy, r, stroke=1, fill=0)
        c.circle(cx2, cy, r, stroke=1, fill=0)
        x_after_inf = x + x_after_w + inf_w

        # "RK" blanco/gris
        c.setFillColor(self.color_w)
        c.setFont("Helvetica-Bold", fs)
        c.drawString(x_after_inf, y + h*0.1, "RK")
        x_after_rk = x_after_inf + c.stringWidth("RK", "Helvetica-Bold", fs)

        # "[IA]" en acento
        c.setFillColor(self.color_accent)
        bracket_fs = fs * 0.85
        c.setFont("Helvetica-Bold", bracket_fs)
        c.drawString(x_after_rk + fs*0.05, y + h*0.1, "[IA]")

        c.restoreState()


# ── Página de portada ─────────────────────────────────────────────────────────
def draw_cover(c, doc):
    c.saveState()
    # Franja azul superior (55%)
    cover_h = H * 0.57
    c.setFillColor(AZUL_OSCURO)
    c.rect(0, H - cover_h, W, cover_h, fill=1, stroke=0)

    # Logo Woorkia en la franja azul
    logo_y = H - cover_h * 0.28
    logo_x = W / 2 - 90
    logo = LogoWoorkia(width=180, height=44, color_w=BLANCO, color_accent=AZUL_CLARO)
    logo.canv = c
    c.saveState()
    c.translate(logo_x, logo_y)
    logo.draw()
    c.restoreState()

    # Línea separadora blanca
    sep_y = H - cover_h * 0.42
    c.setStrokeColor(colors.HexColor("#FFFFFF40"))
    c.setLineWidth(0.5)
    c.line(W*0.15, sep_y, W*0.85, sep_y)

    # "MEMORIA DE DESARROLLO"
    c.setFont("Helvetica-Bold", 26)
    c.setFillColor(BLANCO)
    titulo = "MEMORIA DE DESARROLLO"
    tw = c.stringWidth(titulo, "Helvetica-Bold", 26)
    c.drawString((W - tw)/2, sep_y - 38, titulo)

    # Subtítulo
    c.setFont("Helvetica-Oblique", 12)
    c.setFillColor(colors.HexColor("#BFD4F2"))
    sub = "ADNMotor \u2014 Sistema de Automatizaci\u00f3n de Contenido con IA"
    sw = c.stringWidth(sub, "Helvetica-Oblique", 12)
    c.drawString((W - sw)/2, sep_y - 60, sub)

    # Sección blanca - datos
    info_y = H - cover_h - 20
    line_h = 26

    def info_line(label, value, y):
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(AZUL_OSCURO)
        c.drawString(W*0.18, y, label)
        lw = c.stringWidth(label, "Helvetica-Bold", 11)
        c.setFont("Helvetica", 11)
        c.setFillColor(GRIS_TEXTO)
        c.drawString(W*0.18 + lw + 4, y, value)

    info_line("Cliente:",         "adnmotor.com",                 info_y)
    info_line("Desarrollado por:","Woorkia Consulting",           info_y - line_h)
    info_line("Fecha:",           "28 de marzo de 2026",          info_y - line_h*2)
    info_line("Versi\u00f3n:",    "1.0 \u2014 Estado inicial operativo", info_y - line_h*3)

    # Franja gris inferior
    c.setFillColor(GRIS_FONDO)
    c.rect(0, 0, W, 38, fill=1, stroke=0)
    c.setFont("Helvetica", 9)
    c.setFillColor(GRIS_MEDIO)
    footer_txt = "Pipeline IA  \u2022  WordPress REST API  \u2022  Dashboard de Monitorizaci\u00f3n"
    ftw = c.stringWidth(footer_txt, "Helvetica", 9)
    c.drawString((W - ftw)/2, 13, footer_txt)

    c.restoreState()


# ── Cabecera/Pie páginas de contenido ─────────────────────────────────────────
def draw_content_page(c, doc):
    c.saveState()
    # Cabecera azul
    c.setFillColor(AZUL_OSCURO)
    c.rect(0, H - 28, W, 28, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(BLANCO)
    c.drawString(18, H - 18, "ADNMotor \u2014 Memoria de Desarrollo")
    fecha = "28/03/2026"
    fw = c.stringWidth(fecha, "Helvetica-Bold", 8.5)
    c.drawString(W - fw - 18, H - 18, fecha)

    # Pie
    c.setStrokeColor(GRIS_LINEA)
    c.setLineWidth(0.5)
    c.line(18, 28, W - 18, 28)
    c.setFont("Helvetica", 8)
    c.setFillColor(GRIS_MEDIO)
    pie = "Woorkia Consulting  \u2022  Documento Confidencial"
    pw = c.stringWidth(pie, "Helvetica", 8)
    c.drawString((W - pw)/2, 14, pie)
    # Número de página
    page_num = str(doc.page)
    pnw = c.stringWidth(page_num, "Helvetica", 8)
    c.drawString(W - pnw - 18, 14, page_num)

    c.restoreState()


# ── Estilos ───────────────────────────────────────────────────────────────────
def make_styles():
    base = dict(fontName="Helvetica", leading=14, textColor=GRIS_TEXTO)
    s = {}
    s["h1"] = ParagraphStyle("h1", fontSize=16, fontName="Helvetica-Bold",
                              textColor=AZUL_OSCURO, spaceBefore=18, spaceAfter=4, leading=20)
    s["h2"] = ParagraphStyle("h2", fontSize=12, fontName="Helvetica-Bold",
                              textColor=AZUL_OSCURO, spaceBefore=14, spaceAfter=4, leading=16)
    s["body"] = ParagraphStyle("body", fontSize=10, leading=15,
                                fontName="Helvetica", textColor=GRIS_TEXTO, spaceAfter=6)
    s["bold"] = ParagraphStyle("bold", fontSize=10, leading=15,
                                fontName="Helvetica-Bold", textColor=GRIS_TEXTO, spaceAfter=6)
    s["bullet"] = ParagraphStyle("bullet", fontSize=10, leading=14,
                                  fontName="Helvetica", textColor=GRIS_TEXTO,
                                  leftIndent=14, firstLineIndent=-10, spaceAfter=3)
    s["check"] = ParagraphStyle("check", fontSize=10, leading=14,
                                  fontName="Helvetica", textColor=GRIS_TEXTO,
                                  leftIndent=14, firstLineIndent=-10, spaceAfter=4)
    s["note"] = ParagraphStyle("note", fontSize=9, leading=13,
                                fontName="Helvetica-Oblique", textColor=GRIS_MEDIO, spaceAfter=4)
    s["cell"] = ParagraphStyle("cell", fontSize=9, leading=12,
                                fontName="Helvetica", textColor=GRIS_TEXTO)
    s["cell_hdr"] = ParagraphStyle("cell_hdr", fontSize=9, leading=12,
                                    fontName="Helvetica-Bold", textColor=BLANCO)
    return s


# ── Tabla helper ──────────────────────────────────────────────────────────────
def make_table(headers, rows, col_widths, S):
    data = [[Paragraph(h, S["cell_hdr"]) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), S["cell"]) for c in row])

    style = TableStyle([
        ("BACKGROUND",   (0,0), (-1,0),  AZUL_OSCURO),
        ("FONTNAME",     (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,0),  9),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [BLANCO, GRIS_FONDO]),
        ("GRID",         (0,0), (-1,-1), 0.4, GRIS_LINEA),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ])
    return Table(data, colWidths=col_widths, style=style, repeatRows=1)


def hr():
    return HRFlowable(width="100%", thickness=0.5, color=GRIS_LINEA,
                      spaceAfter=10, spaceBefore=4)


def bullet_item(text, S, icon="•"):
    return Paragraph(f"{icon}  {text}", S["bullet"])


def check_item(text, S, done=False):
    icon = "\u2705" if done else "\u25a1"
    return Paragraph(f"{icon}  {text}", S["check"])


# ── Contenido ─────────────────────────────────────────────────────────────────
def build_content(S):
    story = []
    W_content = A4[0] - 3*cm  # margen usado

    # ─ 1. RESUMEN EJECUTIVO ─
    story.append(Paragraph("1. Resumen Ejecutivo", S["h1"]))
    story.append(hr())
    story.append(Paragraph(
        "ADNMotor ha encargado el desarrollo de un <b>sistema de automatizaci\u00f3n de contenido editorial</b> "
        "basado en Inteligencia Artificial. El objetivo es generar art\u00edculos de automoci\u00f3n de alta calidad SEO "
        "de forma escalable, reduciendo el tiempo de producci\u00f3n de contenido y mejorando el posicionamiento "
        "org\u00e1nico en Google con contenido 100% original.", S["body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph("El sistema realiza el siguiente ciclo de forma autom\u00e1tica:", S["body"]))
    for item in [
        "Captura noticias de automoci\u00f3n de fuentes RSS espa\u00f1olas (Motor.es, Autopista)",
        "Las reescribe completamente con IA \u2014 no es copia, es contenido 100% original",
        "A\u00f1ade im\u00e1genes de calidad buscadas autom\u00e1ticamente por keyword SEO",
        "Las publica como <b>borradores en WordPress</b> para revisi\u00f3n humana antes de publicar",
    ]:
        story.append(bullet_item(item, S))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Capacidad: hasta 30 art\u00edculos/d\u00eda &nbsp;\u2022&nbsp; "
        "Coste estimado: 27\u20ac\u201354\u20ac/mes &nbsp;\u2022&nbsp; "
        "Tasa de \u00e9xito primer d\u00eda: 100%", S["note"]))

    story.append(Spacer(1, 10))

    # ─ 2. ESTADO ACTUAL ─
    story.append(Paragraph("2. Estado Actual del Sistema", S["h1"]))
    story.append(hr())
    story.append(Paragraph("Fecha de revisi\u00f3n: <b>28 de marzo de 2026</b> \u2014 Primer d\u00eda operativo", S["body"]))
    story.append(Spacer(1, 6))
    story.append(make_table(
        ["Componente", "Estado", "Descripci\u00f3n"],
        [
            ["Pipeline RSS",                "\u2705 Operativo",   "Captura 40 art\u00edculos/run de Motor.es y Autopista"],
            ["Generaci\u00f3n IA (Claude)", "\u2705 Operativo",   "Reescribe art\u00edculos en espa\u00f1ol SEO con HTML sem\u00e1ntico"],
            ["Im\u00e1genes Pexels",        "\u2705 Operativo",   "B\u00fasqueda autom\u00e1tica por keyword + subida a WordPress"],
            ["Im\u00e1genes Higgsfield AI", "\u2705 Configurado", "IA regenerativa de im\u00e1genes (pendiente activar)"],
            ["Publicaci\u00f3n WordPress",  "\u2705 Operativo",   "Borradores con imagen destacada y meta SEO RankMath"],
            ["Base de datos SQLite",        "\u2705 Operativa",   "Deduplicaci\u00f3n autom\u00e1tica y logs de ejecuci\u00f3n"],
            ["Dashboard web",              "\u2705 Operativo",   "Panel visual de monitorizaci\u00f3n en tiempo real"],
            ["Automatizaci\u00f3n",         "\U0001f504 Pendiente","Pipeline listo, falta programar ejecuci\u00f3n autom\u00e1tica"],
        ],
        [W_content*0.30, W_content*0.18, W_content*0.52], S
    ))
    story.append(Spacer(1, 12))

    # ─ 3. ARQUITECTURA ─
    story.append(Paragraph("3. Arquitectura del Sistema", S["h1"]))
    story.append(hr())
    story.append(Paragraph("3.1 Estructura de Archivos", S["h2"]))
    story.append(make_table(
        ["Archivo", "Funci\u00f3n"],
        [
            ["main.py",            "Orquestador central del pipeline"],
            ["config.py",          "Configuraci\u00f3n centralizada (APIs, WordPress, fuentes RSS)"],
            ["fetcher.py",         "Descarga y parseo de feeds RSS + web scraping"],
            ["processor.py",       "Integraci\u00f3n con Claude API (generaci\u00f3n de art\u00edculos)"],
            ["publisher.py",       "WordPress REST API client"],
            ["database.py",        "SQLite: deduplicaci\u00f3n y estad\u00edsticas de ejecuci\u00f3n"],
            ["image_processor.py", "Pexels + Higgsfield AI + subida a WordPress Media"],
            ["dashboard.py",       "Panel web Flask de monitorizaci\u00f3n en tiempo real"],
            [".env",               "Credenciales y claves API (protegido, nunca en repositorio)"],
            ["logs/adnmotor.log",  "Registro rotativo de actividad del pipeline"],
        ],
        [W_content*0.30, W_content*0.70], S
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph("3.2 Flujo del Pipeline", S["h2"]))
    pasos = [
        ("1", "FETCH",       "Descarga feeds RSS (~40 art\u00edculos disponibles por run)"),
        ("2", "DEDUPLICATE", "Filtra art\u00edculos ya procesados (SQLite, source_url \u00fanico)"),
        ("3", "LIMIT",       "M\u00e1ximo 5 art\u00edculos por ejecuci\u00f3n (configurable en config.py)"),
        ("4", "PROCESS",     "Claude reescribe completamente en espa\u00f1ol SEO con HTML sem\u00e1ntico"),
        ("5", "IMAGE",       "Pexels busca imagen por keyword \u2192 descarga \u2192 sube a WordPress Media"),
        ("6", "PUBLISH",     "Crea borrador en WordPress con imagen destacada y meta RankMath"),
        ("7", "REGISTRO",    "Guarda en SQLite, actualiza estad\u00edsticas y escribe en log"),
    ]
    for num, tag, desc in pasos:
        story.append(Paragraph(
            f"<b><font color='#1B3A6B'>{num}.</font></b>  "
            f"<b><font color='#2563EB'>{tag}</font></b> \u2014 {desc}", S["bullet"]))
    story.append(Spacer(1, 12))

    # ─ 4. APIS ─
    story.append(Paragraph("4. Credenciales y APIs Configuradas", S["h1"]))
    story.append(hr())
    story.append(make_table(
        ["Servicio", "Estado", "Uso en el sistema"],
        [
            ["Anthropic Claude (claude-sonnet-4-6)", "\u2705 Activo",     "Generaci\u00f3n de art\u00edculos con IA"],
            ["WordPress REST API v2",                "\u2705 Activo",     "Publicaci\u00f3n en adnmotor.com"],
            ["Pexels API",                           "\u2705 Activo",     "Im\u00e1genes stock libres de copyright"],
            ["Higgsfield AI API",                    "\u2705 Configurado","Regeneraci\u00f3n IA de im\u00e1genes (pendiente activar)"],
        ],
        [W_content*0.38, W_content*0.20, W_content*0.42], S
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<b>Nota:</b> La conexi\u00f3n a WordPress usa <i>Application Password</i> (no la contrase\u00f1a de cuenta). "
        "Los art\u00edculos se publican bajo el usuario <b>996098pwpadmin</b>, autor principal del blog.", S["note"]))
    story.append(Spacer(1, 12))

    # ─ 5. ESTADÍSTICAS ─
    story.append(Paragraph("5. Rendimiento y Estad\u00edsticas", S["h1"]))
    story.append(hr())
    story.append(Paragraph("5.1 Primer D\u00eda Operativo (28/03/2026)", S["h2"]))
    story.append(make_table(
        ["M\u00e9trica", "Valor"],
        [
            ["Art\u00edculos publicados como borradores", "13 art\u00edculos"],
            ["Tasa de \u00e9xito",                       "100% (0 fallos permanentes)"],
            ["Fuentes activas",                          "Motor.es + Autopista = ~40 art/run"],
            ["Art\u00edculos por ejecuci\u00f3n",         "5 (configurable)"],
            ["Ejecuciones realizadas",                   "3 runs manuales de prueba"],
        ],
        [W_content*0.55, W_content*0.45], S
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph("5.2 Capacidad y Costes Estimados", S["h2"]))
    story.append(make_table(
        ["Escenario", "Art\u00edculos/d\u00eda", "Coste/d\u00eda", "Coste/mes"],
        [
            ["Moderado (2 runs/d\u00eda)", "10", "~0,40\u20ac", "~12\u20ac"],
            ["Normal (4 runs/d\u00eda)",   "20", "~0,80\u20ac", "~24\u20ac"],
            ["M\u00e1ximo (6 runs/d\u00eda)","30", "~1,20\u20ac", "~36\u20ac"],
        ],
        [W_content*0.40, W_content*0.20, W_content*0.20, W_content*0.20], S
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Coste unitario estimado por art\u00edculo con Claude Sonnet: 0,03\u20ac \u2013 0,06\u20ac", S["note"]))
    story.append(Spacer(1, 12))

    # ─ 6. DASHBOARD ─
    story.append(Paragraph("6. Dashboard de Monitorizaci\u00f3n", S["h1"]))
    story.append(hr())
    story.append(Paragraph(
        "Panel web accesible en <b>http://localhost:5000</b> con acceso visual completo al estado del sistema:", S["body"]))
    for item in [
        "Estad\u00edsticas en tiempo real: art\u00edculos hoy, semana, total y tasa de \u00e9xito",
        "Gr\u00e1fico de barras de los \u00faltimos 7 d\u00edas de actividad del pipeline",
        "Listado de \u00faltimos borradores publicados con enlace directo a WordPress",
        "Log de actividad en tiempo real (mismo contenido que adnmotor.log)",
        "Secci\u00f3n de automatizaci\u00f3n con control del Task Scheduler de Windows",
    ]:
        story.append(bullet_item(item, S))
    story.append(Spacer(1, 12))

    # ─ 7. PRÓXIMOS PASOS ─
    story.append(Paragraph("7. Pr\u00f3ximos Pasos", S["h1"]))
    story.append(hr())
    story.append(Paragraph("7.1 Inmediato \u2014 Esta Semana", S["h2"]))
    for t in [
        "Activar Task Scheduler \u2014 ejecuci\u00f3n autom\u00e1tica cada 4 horas en Windows",
        "Revisar los 13 borradores en WordPress Admin \u2192 Entradas \u2192 Borradores",
        "Publicar los art\u00edculos que superen la revisi\u00f3n humana de calidad",
        "Instalar mu-plugin de RankMath para guardar meta fields SEO v\u00eda API",
    ]:
        story.append(check_item(t, S))
    story.append(Spacer(1, 6))
    story.append(Paragraph("7.2 Corto Plazo \u2014 2\u20134 Semanas", S["h2"]))
    for t in [
        "Activar Higgsfield AI para regeneraci\u00f3n de im\u00e1genes con IA (100% libres de copyright)",
        "A\u00f1adir m\u00e1s fuentes RSS: Km77.com, Motorpasion.es, Coches.net",
        "Ampliar a 10 art\u00edculos/run cuando se valide la calidad del contenido",
        "Mover el sistema a un VPS para funcionamiento 24/7 independiente del PC",
    ]:
        story.append(check_item(t, S))
    story.append(Spacer(1, 6))
    story.append(Paragraph("7.3 Medio Plazo \u2014 1\u20132 Meses", S["h2"]))
    for t in [
        "Integraci\u00f3n con Google Search Console para detectar keywords que ya rankean",
        "Sistema de categorizaci\u00f3n autom\u00e1tica mejorado (pruebas, comparativas, gu\u00edas)",
        "Publicaci\u00f3n directa (sin borrador) para art\u00edculos de alta confianza",
        "Alertas por email/Telegram cuando falla una ejecuci\u00f3n del pipeline",
        "Dashboard accesible online (Vercel/Railway) para acceso desde cualquier lugar",
    ]:
        story.append(check_item(t, S))
    story.append(Spacer(1, 12))

    # ─ 8. GUÍA RÁPIDA ─
    story.append(Paragraph("8. Gu\u00eda de Uso R\u00e1pido", S["h1"]))
    story.append(hr())
    story.append(make_table(
        ["Acci\u00f3n", "C\u00f3mo hacerlo"],
        [
            ["Ejecutar el pipeline manualmente",  "Terminal en la carpeta del proyecto \u2192 python main.py"],
            ["Ver el dashboard",                  "python dashboard.py \u2192 abrir http://localhost:5000"],
            ["Ver borradores en WordPress",       "WP Admin \u2192 Entradas \u2192 Borradores"],
            ["Ajustar art\u00edculos por run",    "config.py \u2192 MAX_ARTICLES_PER_RUN (actual: 5)"],
            ["A\u00f1adir fuente RSS",            "config.py \u2192 RSS_FEEDS \u2192 {name, url, category_hint}"],
            ["Cambiar proveedor im\u00e1genes",   ".env \u2192 IMAGE_PROVIDER=pexels o higgsfield"],
            ["Consultar logs",                    "logs/adnmotor.log o dashboard web"],
        ],
        [W_content*0.38, W_content*0.62], S
    ))
    story.append(Spacer(1, 12))

    # ─ 9. TECNOLOGÍAS ─
    story.append(Paragraph("9. Tecnolog\u00edas Utilizadas", S["h1"]))
    story.append(hr())
    story.append(make_table(
        ["Tecnolog\u00eda", "Versi\u00f3n", "Uso en el proyecto"],
        [
            ["Python",                "3.11+",             "Lenguaje principal del backend y pipeline"],
            ["Anthropic Claude",      "claude-sonnet-4-6", "Generaci\u00f3n de contenido con IA"],
            ["Flask",                 "3.0+",              "Framework del dashboard web"],
            ["SQLite",                "3.x",               "Base de datos local para deduplicaci\u00f3n y logs"],
            ["feedparser",            "6.0+",              "Parseo de feeds RSS de las fuentes"],
            ["BeautifulSoup4",        "4.12+",             "Web scraping HTML para extraer contenido"],
            ["requests",              "2.31+",             "Llamadas HTTP a APIs externas"],
            ["python-dotenv",         "1.0+",              "Gesti\u00f3n segura de credenciales"],
            ["WordPress REST API",    "v2",                "Publicaci\u00f3n de borradores en adnmotor.com"],
            ["Pexels API",            "v1",                "Im\u00e1genes stock gratuitas y libres"],
            ["Higgsfield AI API",     "v1",                "Regeneraci\u00f3n IA de im\u00e1genes"],
        ],
        [W_content*0.30, W_content*0.20, W_content*0.50], S
    ))

    return story


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    out = r"C:\Users\samue\OneDrive\Escritorio\Mario ADNMotor\Memoria_Desarrollo_ADNMotor.pdf"

    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, NextPageTemplate as NPT

    frames_cover = [Frame(0, 0, W, H, leftPadding=0, rightPadding=0,
                          topPadding=0, bottomPadding=0, id="cover_frame")]
    frames_content = [Frame(1.5*cm, 1.5*cm, W - 3*cm, H - 3.8*cm,
                            leftPadding=0, rightPadding=0,
                            topPadding=8, bottomPadding=8, id="content_frame")]

    cover_tpl   = PageTemplate(id="cover",   frames=frames_cover,   onPage=draw_cover)
    content_tpl = PageTemplate(id="content", frames=frames_content, onPage=draw_content_page)

    doc = BaseDocTemplate(
        out,
        pagesize=A4,
        pageTemplates=[cover_tpl, content_tpl],
        title="Memoria de Desarrollo \u2014 ADNMotor",
        author="Woorkia Consulting",
        subject="ADNMotor Automation Pipeline",
    )

    S = make_styles()

    full_story = (
        [Spacer(1, H * 0.72)]
        + [NPT("content"), PageBreak()]
        + build_content(S)
    )

    doc.build(full_story)
    size = os.path.getsize(out) / 1024
    print(f"\nOK - PDF generado: {out}")
    print(f"   Tamano: {size:.1f} KB")


if __name__ == "__main__":
    main()
