import time
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque, Counter

# ---------------------------------------------------------------------------
# CONFIGURACIÓN GLOBAL
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

MAX_PAGINAS_DEFAULT = 50

# ---------------------------------------------------------------------------
# Fragmentos de URL que indican páginas NO relacionadas con ofertas de trabajo.
# Si la URL contiene alguno de estos segmentos, se descarta antes de visitarla.
# ---------------------------------------------------------------------------
_URL_BLACKLIST: set[str] = {
    "login", "logout", "register", "signup", "sign-up", "sign_up",
    "password", "reset", "forgot", "account", "profile", "settings",
    "cart", "checkout", "shop", "tienda", "producto", "product",
    "contacto", "contact", "about", "nosotros", "quienes-somos",
    "terminos", "terms", "privacidad", "privacy", "cookies", "legal",
    "ayuda", "help", "faq", "soporte", "support",
    "blog", "news", "noticias", "articulo", "article",
    "gallery", "galeria", "media", "video", "foto",
    "sitemap", "rss", "feed", "cdn", "static",
    "facebook", "twitter", "instagram", "linkedin", "youtube",
    "wp-admin", "wp-login", "wp-content",
    "wp-json",
}

# ---------------------------------------------------------------------------
# Señales en la URL que sugieren que es una oferta de empleo.
# Al menos una de estas debe aparecer para encolar la página.
# Si la URL no contiene ninguna Y tampoco es la raíz, se descarta.
# ---------------------------------------------------------------------------
_URL_EMPLEO_SIGNALS: set[str] = {
    "empleo", "empleo", "trabajo", "oferta", "vacante", "puesto",
    "job", "jobs", "career", "careers", "position", "opening",
    "bolsa", "reclutamiento", "recruitment", "oportunidad",
    "aplica", "apply", "postula", "postulate",
}

# ---------------------------------------------------------------------------
# Palabras que deben aparecer en el TEXTO de la página para considerarla
# una oferta de empleo válida.
# ---------------------------------------------------------------------------
_TEXTO_EMPLEO_SIGNALS: list[str] = [
    "requisitos", "funciones", "responsabilidades", "beneficios",
    "experiencia", "habilidades", "perfil", "postular", "aplicar",
    "contrato", "jornada", "horario", "salario", "sueldo",
    "requirements", "responsibilities", "benefits", "apply", "job",
    "position", "candidate", "hiring", "vacancy",
]

# ---------------------------------------------------------------------------
# Categorías con sus palabras clave
# ---------------------------------------------------------------------------
_CATEGORIAS: dict[str, list[str]] = {
    "Tecnología": [
        "tecnologia", "it", "tech", "software", "developer", "programacion",
        "data", "sistemas", "fullstack", "backend", "frontend", "ingeniero",
        "devops", "cloud", "ciberseguridad", "inteligencia artificial",
    ],
    "Ventas": [
        "ventas", "sales", "comercial", "retail", "negocios", "vendedor",
        "ejecutivo", "promotor", "asesor",
    ],
    "Marketing": [
        "marketing", "publicidad", "seo", "sem", "social media", "comunicacion",
        "digital", "branding", "copywriter", "community",
    ],
    "Diseño y Creatividad": [
        "diseno", "design", "ux", "ui", "creativo", "arte", "ilustrador",
        "grafico", "video", "animacion",
    ],
    "Finanzas": [
        "finanzas", "contabilidad", "finance", "accounting", "banca",
        "auditoria", "contador", "tesoreria", "credito",
    ],
    "Recursos Humanos": [
        "rrhh", "recursos humanos", "hr", "talent", "recruitment",
        "personal", "reclutamiento", "nominas", "capacitacion",
    ],
    "Administración": [
        "administracion", "admin", "operaciones", "operations", "oficina",
        "asistente", "recepcionista", "secretaria", "coordinador",
    ],
    "Atención al Cliente": [
        "atencion", "customer", "soporte", "support", "service",
        "call center", "ayuda", "recepcion", "cajero",
    ],
    "Salud y Medicina": [
        "salud", "medica", "health", "medical", "clinica", "enfermeria",
        "doctor", "odontologia", "psicologia", "farmacia",
    ],
    "Educación": [
        "educacion", "education", "profesor", "teacher", "formacion",
        "docente", "taller", "instructor", "tutor",
    ],
    "Legal": [
        "legal", "derecho", "abogado", "law", "juridico", "leyes", "notaria",
    ],
    "Logística y Transporte": [
        "logistica", "transporte", "almacen", "bodega", "distribucion",
        "mensajero", "conductor", "repartidor", "importacion",
    ],
    "Producción e Industria": [
        "produccion", "manufactura", "planta", "operario", "ensamble",
        "calidad", "mantenimiento", "mecanico", "electrico", "industrial",
    ],
}


# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------

def normalizar_url(url: str) -> str:
    """Asegura que la URL tenga el esquema https."""
    url = url.strip()
    return url if url.startswith(("http://", "https://")) else "https://" + url


def limpiar_url(url: str) -> str:
    """Elimina fragmentos (#) y barras finales para evitar duplicados."""
    return url.split("#")[0].rstrip("/") or url


def _url_en_blacklist(url: str) -> bool:
    """Devuelve True si algún segmento de la URL está en la blacklist."""
    partes = set(re.split(r"[/\-_?=&.]", url.lower()))
    return bool(partes & _URL_BLACKLIST)


def _url_parece_oferta(url: str, es_raiz: bool) -> bool:
    """
    Devuelve True si la URL tiene señales de ser una oferta o una sección
    de empleos. Las raíces y secciones generales de empleo también se aceptan
    para que el crawler pueda descubrir las páginas hijas.
    """
    url_lower = url.lower()
    return es_raiz or any(s in url_lower for s in _URL_EMPLEO_SIGNALS)


def _texto_parece_oferta(texto: str) -> bool:
    """
    Devuelve True si el texto visible de la página contiene al menos
    2 señales de ser una oferta de empleo real.
    """
    texto_lower = texto.lower()
    hits = sum(1 for s in _TEXTO_EMPLEO_SIGNALS if s in texto_lower)
    return hits >= 2


def _clasificar_categoria(url: str, texto: str) -> str:
    """Asigna la categoría más probable basándose en URL y texto."""
    url_lower = url.lower()
    texto_lower = texto[:2000].lower()  # Solo primeros 2000 chars para velocidad
    for categoria, keywords in _CATEGORIAS.items():
        if any(k in url_lower for k in keywords) or any(k in texto_lower for k in keywords):
            return categoria
    return "General"


def _extraer_precio(texto: str) -> float | None:
    """Intenta extraer un salario numérico del texto visible de la página."""
    patrones = [
        r"[$€£]\s?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)",
        r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s?[$€£]",
        r"(?:salario|sueldo|paga|salary)[:\s]*([$€£]?\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)",
    ]
    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if not match:
            continue
        try:
            raw = (
                match.group(1)
                .replace("$", "").replace("€", "").replace("£", "")
                .strip()
            )
            # Normalizar separadores
            if "," in raw and "." in raw:
                if raw.find(".") < raw.find(","):   # 1.234,56 → 1234.56
                    raw = raw.replace(".", "").replace(",", ".")
                else:                                # 1,234.56 → 1234.56
                    raw = raw.replace(",", "")
            elif "," in raw:
                raw = raw.replace(",", ".")

            val = float(raw)
            if 100 < val < 1_000_000:
                return val
        except ValueError:
            continue
    return None


def _extraer_titulo(soup: BeautifulSoup) -> str:
    """
    Intenta obtener el título más representativo de la oferta.
    Prioriza meta og:title, luego <title>, luego el primer h1/h2.
    """
    # 1. Open Graph title (más preciso en portales de empleo)
    og = soup.find("meta", property="og:title")
    if og and og.get("content", "").strip():
        return og["content"].strip()

    # 2. <title> de la página (quitar sufijos tipo " | Portal Empleo")
    if soup.title and soup.title.string:
        titulo = soup.title.string.strip()
        # Eliminar sufijo del sitio (ej. " - MiEmpleo.com")
        titulo = re.split(r"\s[\|\-–—]\s", titulo)[0].strip()
        if titulo:
            return titulo

    # 3. Primer encabezado visible
    for tag in ("h1", "h2"):
        found = soup.find(tag)
        if found and found.get_text(strip=True):
            return found.get_text(strip=True)

    return "Sin título"


# ---------------------------------------------------------------------------
# CLASE PRINCIPAL
# ---------------------------------------------------------------------------

class CrawlerEmpleo:
    """Navega un dominio y extrae únicamente páginas de ofertas de empleo."""

    def __init__(self, url_principal: str):
        self.url_principal = normalizar_url(url_principal)
        self.dominio = urlparse(self.url_principal).netloc
        self.visitadas: set[str] = set()
        self.pendientes: deque[str] = deque([limpiar_url(self.url_principal)])
        self.datos_recopilados: list[dict] = []

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _es_enlace_interno(self, url: str) -> bool:
        return urlparse(url).netloc == self.dominio

    def _extraer_enlaces_internos(self, soup: BeautifulSoup, url_actual: str) -> list[str]:
        """Extrae enlaces internos del dominio, aplicando filtros de calidad."""
        enlaces: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("mailto:", "javascript:", "tel:", "#")):
                continue

            url_abs = limpiar_url(urljoin(url_actual, href))

            # Descartar si no pertenece al dominio
            if not self._es_enlace_interno(url_abs):
                continue

            # Descartar URLs de páginas irrelevantes (login, about, etc.)
            if _url_en_blacklist(url_abs):
                continue

            # Solo encolar si la URL parece una sección o ficha de empleo
            es_raiz = urlparse(url_abs).path in ("", "/")
            if _url_parece_oferta(url_abs, es_raiz):
                enlaces.append(url_abs)

        return enlaces

    def _extraer_datos_pagina(self, soup: BeautifulSoup, url: str) -> None:
        """Guarda los datos de la página SOLO si parece una oferta real."""
        texto_pagina = soup.get_text(separator=" ", strip=True)

        # ── Validación: ¿es realmente una oferta de empleo? ────────────────
        if not _texto_parece_oferta(texto_pagina):
            return  # Descartamos páginas genéricas aunque pasaron el filtro de URL

        titulo = _extraer_titulo(soup)
        precio = _extraer_precio(texto_pagina)
        categoria = _clasificar_categoria(url, texto_pagina)

        self.datos_recopilados.append({
            "URL": url,
            "Titulo": titulo,
            "Precio": precio,
            "Categoria": categoria,
            "Descripcion": texto_pagina[:1500],
        })

    def _agregar_enlaces(self, enlaces: list[str]) -> None:
        for url in enlaces:
            if url not in self.visitadas and url not in self.pendientes:
                self.pendientes.append(url)

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------

    def recorrer(
        self,
        max_paginas: int = MAX_PAGINAS_DEFAULT,
        callback=None,
    ) -> pd.DataFrame:
        """
        Inicia el crawling hasta alcanzar el límite de páginas.

        :param max_paginas: Máximo de páginas a visitar (no todas se guardan).
        :param callback: Función para reportar progreso en la UI.
        :return: DataFrame con las ofertas encontradas.
        """
        paginas_visitadas = 0

        if callback:
            callback(
                f"Iniciando crawler desde: {self.url_principal}\n"
                f"Límite de páginas: {max_paginas}"
            )

        while self.pendientes and paginas_visitadas < max_paginas:
            url = self.pendientes.popleft()

            if url in self.visitadas:
                continue

            self.visitadas.add(url)
            paginas_visitadas += 1

            if callback:
                callback(
                    f"[{paginas_visitadas}/{max_paginas}] "
                    f"Visitando: {url}"
                )

            try:
                respuesta = requests.get(url, headers=HEADERS, timeout=15)

                if respuesta.status_code != 200:
                    if callback:
                        callback(f"[HTTP {respuesta.status_code}] Saltando: {url}")
                    continue

                soup = BeautifulSoup(respuesta.text, "html.parser")
                self._extraer_datos_pagina(soup, url)
                enlaces = self._extraer_enlaces_internos(soup, url)
                self._agregar_enlaces(enlaces)

                time.sleep(0.8)  # Retraso cortés al servidor

            except requests.exceptions.RequestException as err:
                if callback:
                    callback(f"[ERROR RED] {url}: {err}")

        total_ofertas = len(self.datos_recopilados)
        if callback:
            callback(
                f"Crawler finalizado. "
                f"Páginas visitadas: {len(self.visitadas)} | "
                f"Ofertas encontradas: {total_ofertas}"
            )

        return pd.DataFrame(self.datos_recopilados)


# ---------------------------------------------------------------------------
# MINERÍA DE DATOS (CONSOLA)
# ---------------------------------------------------------------------------

def mineria_de_datos(df: pd.DataFrame) -> None:
    """Análisis básico de los datos extraídos; muestra resultados en consola."""
    print("\n" + "=" * 50)
    print(" RESULTADOS DE MINERÍA DE DATOS (CONSOLA)")
    print("=" * 50)

    if df.empty:
        print(" No hay datos para analizar.")
        return

    df_precios = df.dropna(subset=["Precio"])
    if not df_precios.empty:
        print(f"\n Análisis de Sueldos:")
        print(f"   Promedio : ${df_precios['Precio'].mean():,.2f}")
        print(f"   Mínimo   : ${df_precios['Precio'].min():,.2f}")
        print(f"   Máximo   : ${df_precios['Precio'].max():,.2f}")
    else:
        print("\n No se detectaron salarios válidos.")

    print("\n Palabras más frecuentes en Títulos:")
    texto = " ".join(df["Titulo"].astype(str)).lower()
    palabras = re.findall(r"\b[a-záéíóúñ]{4,}\b", texto)
    for palabra, frec in Counter(palabras).most_common(5):
        print(f"   {palabra.capitalize()}: {frec}")

    print("\n Distribución por Categoría:")
    for cat, cant in df["Categoria"].value_counts().items():
        print(f"   {cat}: {cant} ({cant / len(df) * 100:.1f}%)")


# ---------------------------------------------------------------------------
# ENTRY POINT (consola)
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("PROYECTO 3 — Crawler de Empleo")
    print("=" * 60)

    url = input("\n Ingrese la URL principal: ").strip()
    if not url:
        return

    max_p = input(f" Máximo de páginas (default {MAX_PAGINAS_DEFAULT}): ").strip()
    limite = int(max_p) if max_p.isdigit() else MAX_PAGINAS_DEFAULT

    crawler = CrawlerEmpleo(url)
    df = crawler.recorrer(max_paginas=limite, callback=print)

    df.to_csv("datos_extraidos.csv", index=False, encoding="utf-8")
    print("\n Datos guardados en 'datos_extraidos.csv'")

    mineria_de_datos(df)


if __name__ == "__main__":
    main()