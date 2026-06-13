import time
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque, Counter

# Configuración global
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

MAX_PAGINAS_DEFAULT = 50


def normalizar_url(url: str) -> str:
    """Asegura que la URL tenga el esquema http o https."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def limpiar_url(url: str) -> str:
    """Elimina fragmentos (#) y barras finales de la URL para evitar duplicados."""
    return url.split("#")[0].rstrip("/") or url


class CrawlerEmpleo:
    """
    Clase encargada de navegar por un dominio específico y extraer datos de empleo.
    """

    def __init__(self, url_principal: str):
        """
        Inicializa el crawler con una URL base.
        :param url_principal: URL desde donde comenzará la navegación.
        """
        self.url_principal = normalizar_url(url_principal)
        self.dominio = urlparse(self.url_principal).netloc
        self.visitadas: set[str] = set()
        self.pendientes: deque[str] = deque([limpiar_url(self.url_principal)])
        self.datos_recopilados: list[dict] = []

    def _es_enlace_interno(self, url: str) -> bool:
        """Verifica si un enlace pertenece al mismo dominio que la URL principal."""
        return urlparse(url).netloc == self.dominio

    def _extraer_enlaces_internos(self, soup: BeautifulSoup, url_actual: str) -> list[str]:
        """Extrae todos los enlaces <a> de una página que apunten al mismo dominio."""
        enlaces = []
        for enlace in soup.find_all("a", href=True):
            href = enlace.get("href", "").strip()
            # Ignorar enlaces irrelevantes
            if not href or href.startswith(("mailto:", "javascript:", "tel:", "#")):
                continue

            url_absoluta = limpiar_url(urljoin(url_actual, href))
            if self._es_enlace_interno(url_absoluta):
                enlaces.append(url_absoluta)

        return enlaces

    def _extraer_datos_pagina(self, soup: BeautifulSoup, url: str) -> None:
        """
        Analiza el contenido de una página para extraer título, salario y categoría.
        """
        # Extraer título (priorizando h1 o h2)
        titulo_tag = soup.find(["h1", "h2"])
        titulo = titulo_tag.text.strip() if titulo_tag else "Sin título"

        # Obtener todo el texto visible para buscar salarios y palabras clave
        texto_pagina = soup.get_text(separator=' ', strip=True)

        # Extracción de Salario/Precio (Mejorada)
        precio = None
        patrones_salario = [
            r'[$€£]\s?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', # Símbolo antes
            r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s?[$€£]', # Símbolo después
            r'(?:salario|sueldo|paga)[:\s]*([$€£]?\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', # Palabra clave
        ]
        
        for patron in patrones_salario:
            match = re.search(patron, texto_pagina, re.IGNORECASE)
            if match:
                try:
                    # Limpieza agresiva del valor numérico
                    valor_str = match.group(1).replace('$', '').replace('€', '').replace('£', '').strip()
                    # Normalización de separadores decimales/miles
                    if ',' in valor_str and '.' in valor_str:
                        if valor_str.find('.') < valor_str.find(','): # 1.234,56 -> 1234.56
                            valor_str = valor_str.replace('.', '').replace(',', '.')
                        else: # 1,234.56 -> 1234.56
                            valor_str = valor_str.replace(',', '')
                    elif ',' in valor_str:
                        valor_str = valor_str.replace(',', '.')
                    
                    val = float(valor_str)
                    if 100 < val < 1000000: # Rango razonable para salarios mensuales/anuales
                        precio = val
                        break
                except ValueError:
                    continue

        # Categorización Inteligente
        categoria = "General"
        url_lower = url.lower()
        texto_lower = texto_pagina.lower()
        
        categorias_keywords = {
            "Tecnología": ["tecnologia", "it", "tech", "software", "developer", "programacion", "data", "sistemas", "fullstack", "backend", "frontend", "ingeniero"],
            "Ventas": ["ventas", "sales", "comercial", "retail", "negocios", "vendedor", "ejecutivo", "promotor"],
            "Marketing": ["marketing", "publicidad", "seo", "sem", "social-media", "comunicacion", "digital", "branding", "copywriter"],
            "Diseño y Creatividad": ["diseno", "design", "ux", "ui", "creativo", "arte", "ilustrador", "grafico", "video"],
            "Finanzas": ["finanzas", "contabilidad", "finance", "accounting", "banca", "auditoria", "contador", "tesoreria"],
            "Recursos Humanos": ["rrhh", "recursos-humanos", "hr", "talent", "recruitment", "personal", "reclutamiento", "nominas"],
            "Administración": ["administracion", "admin", "operaciones", "operations", "oficina", "asistente", "recepcionista"],
            "Atención al Cliente": ["atencion", "customer", "soporte", "support", "service", "call-center", "ayuda", "recepcion"],
            "Salud y Medicina": ["salud", "medica", "health", "medical", "clinica", "enfermeria", "doctor", "odontologia", "psicologia"],
            "Educación": ["educacion", "education", "profesor", "teacher", "formacion", "docente", "taller", "instructor"],
            "Legal": ["legal", "derecho", "abogado", "law", "juridico", "leyes", "notaria"]
        }

        for cat, keywords in categorias_keywords.items():
            if any(k in url_lower for k in keywords) or any(k in texto_lower[:1000] for k in keywords):
                categoria = cat
                break

        # Almacenar datos
        self.datos_recopilados.append({
            "URL": url,
            "Titulo": titulo,
            "Precio": precio,
            "Categoria": categoria,
            "Descripcion": texto_pagina[:1000] # Fragmento para análisis de palabras clave
        })

    def _agregar_enlaces(self, enlaces: list[str]) -> None:
        """Añade nuevos enlaces a la cola de pendientes si no han sido visitados."""
        for url in enlaces:
            if url not in self.visitadas and url not in self.pendientes:
                self.pendientes.append(url)

    def recorrer(self, max_paginas: int = MAX_PAGINAS_DEFAULT, callback=None) -> pd.DataFrame:
        """
        Inicia el proceso de crawling hasta alcanzar el límite de páginas.
        :param max_paginas: Cantidad máxima de páginas a visitar.
        :param callback: Función opcional para reportar el progreso (útil para la UI).
        :return: DataFrame con los datos extraídos.
        """
        paginas_visitadas = 0

        msg_inicio = f" Iniciando crawler desde: {self.url_principal}\n🔍 Límite de páginas: {max_paginas}\n"
        if callback: callback(msg_inicio)

        while self.pendientes and paginas_visitadas < max_paginas:
            url = self.pendientes.popleft()

            if url in self.visitadas:
                continue

            self.visitadas.add(url)
            paginas_visitadas += 1
            log_msg = f" [{paginas_visitadas}/{max_paginas}] Visitando: {url}"
            if callback: callback(log_msg)

            try:
                # Realizar petición HTTP con timeout
                respuesta = requests.get(url, headers=HEADERS, timeout=15)

                if respuesta.status_code != 200:
                    err_msg = f" [ERROR] Código HTTP {respuesta.status_code} en {url}"
                    if callback: callback(err_msg)
                    continue

                # Parsear contenido HTML
                soup = BeautifulSoup(respuesta.text, "html.parser")
                
                # Extraer datos y nuevos enlaces
                self._extraer_datos_pagina(soup, url)
                enlaces = self._extraer_enlaces_internos(soup, url)
                self._agregar_enlaces(enlaces)
                
                # Respetar el sitio con un pequeño retraso
                time.sleep(1)

            except requests.exceptions.RequestException as error:
                err_msg = f"🔌 [ERROR RED] {url}: {error}"
                if callback: callback(err_msg)

        msg_fin = f"\n Crawler finalizado. Páginas analizadas: {len(self.visitadas)}"
        if callback: callback(msg_fin)
        
        return pd.DataFrame(self.datos_recopilados)


def mineria_de_datos(df: pd.DataFrame) -> None:
    """
    Realiza un análisis de datos sobre el DataFrame y muestra resultados en consola.
    """
    print("\n" + "=" * 50)
    print(" RESULTADOS DE MINERÍA DE DATOS (CONSOLA)")
    print("=" * 50)

    if df.empty:
        print(" No hay datos para analizar.")
        return

    # Análisis de Salarios
    df_precios = df.dropna(subset=['Precio'])
    if not df_precios.empty:
        print(f"\n Análisis de Sueldos:")
        print(f" • Promedio: ${df_precios['Precio'].mean():,.2f}")
        print(f" • Rango: ${df_precios['Precio'].min():,.2f} - ${df_precios['Precio'].max():,.2f}")
    else:
        print("\n No se detectaron salarios válidos.")

    # Palabras clave en Títulos
    print("\n Palabras más frecuentes en Títulos:")
    texto_titulos = " ".join(df['Titulo'].astype(str)).lower()
    palabras = re.findall(r'\b[a-záéíóúñ]{4,}\b', texto_titulos)
    for palabra, frec in Counter(palabras).most_common(5):
        print(f" • {palabra.capitalize()}: {frec}")

    # Distribución por Categoría
    print("\n Distribución por Categoría:")
    frec_cat = df['Categoria'].value_counts()
    for cat, cant in frec_cat.items():
        print(f" • {cat}: {cant} ({ (cant/len(df))*100:.1f}%)")


def main() -> None:
    """Función de entrada para ejecución por consola."""
    print("=" * 60)
    print("PROYECTO 3 - Crawler de Empleo")
    print("=" * 60)

    url = input("\n Ingrese la URL principal: ").strip()
    if not url:
        return

    max_p = input(f" Máximo de páginas (default {MAX_PAGINAS_DEFAULT}): ").strip()
    limite = int(max_p) if max_p.isdigit() else MAX_PAGINAS_DEFAULT

    crawler = CrawlerEmpleo(url)
    df = crawler.recorrer(max_paginas=limite, callback=print)

    # Guardar persistencia
    df.to_csv("datos_extraidos.csv", index=False, encoding='utf-8')
    print(f"\n Datos guardados en 'datos_extraidos.csv'")

    mineria_de_datos(df)


if __name__ == "__main__":
    main()