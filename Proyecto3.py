import time
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque, Counter

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
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def limpiar_url(url: str) -> str:
    return url.split("#")[0].rstrip("/") or url


class CrawlerEmpleo:

    def __init__(self, url_principal: str):
        self.url_principal = normalizar_url(url_principal)
        self.dominio = urlparse(self.url_principal).netloc
        self.visitadas: set[str] = set()
        self.pendientes: deque[str] = deque([limpiar_url(self.url_principal)])
        self.datos_recopilados: list[dict] = []

    def _es_enlace_interno(self, url: str) -> bool:
        return urlparse(url).netloc == self.dominio

    def _extraer_enlaces_internos(self, soup: BeautifulSoup, url_actual: str) -> list[str]:
        enlaces = []
        for enlace in soup.find_all("a", href=True):
            href = enlace.get("href", "").strip()
            if not href or href.startswith(("mailto:", "javascript:", "tel:", "#")):
                continue

            url_absoluta = limpiar_url(urljoin(url_actual, href))
            if self._es_enlace_interno(url_absoluta):
                enlaces.append(url_absoluta)

        return enlaces

    def _extraer_datos_pagina(self, soup: BeautifulSoup, url: str) -> None:
        
        titulo_tag = soup.find(["h1", "h2"])
        titulo = titulo_tag.text.strip() if titulo_tag else "Sin título"

        texto_pagina = soup.get_text(separator=' ', strip=True)

        precio = None
        patron_precio = re.findall(r'[$€]\s?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', texto_pagina)
        if patron_precio:
            try:
                precio_limpio = patron_precio[0].replace(',', '').replace('.', '')
                precio = float(precio_limpio)
            except ValueError:
                pass

        categoria = "General"
        url_lower = url.lower()
        
        if any(k in url_lower for k in ["tecnologia", "it", "tech", "software", "developer", "programacion", "data"]):
            categoria = "Tecnología"
            
        elif any(k in url_lower for k in ["ventas", "sales", "comercial", "retail", "negocios"]):
            categoria = "Ventas"
            
        elif any(k in url_lower for k in ["marketing", "publicidad", "seo", "sem", "social-media", "comunicacion"]):
            categoria = "Marketing"
            
        elif any(k in url_lower for k in ["diseno", "design", "ux", "ui", "creativo", "arte"]):
            categoria = "Diseño y Creatividad"
            
        elif any(k in url_lower for k in ["finanzas", "contabilidad", "finance", "accounting", "banca", "auditoria"]):
            categoria = "Finanzas y Contabilidad"
            
        elif any(k in url_lower for k in ["rrhh", "recursos-humanos", "hr", "talent", "recruitment", "personal"]):
            categoria = "Recursos Humanos"
            
        elif any(k in url_lower for k in ["administracion", "admin", "operaciones", "operations", "oficina"]):
            categoria = "Administración y Operaciones"
            
        elif any(k in url_lower for k in ["atencion", "customer", "soporte", "support", "service", "call-center"]):
            categoria = "Atención al Cliente"
            
        elif any(k in url_lower for k in ["salud", "medica", "health", "medical", "clinica", "enfermeria"]):
            categoria = "Salud y Medicina"
            
        elif any(k in url_lower for k in ["educacion", "education", "profesor", "teacher", "formacion", "docente"]):
            categoria = "Educación y Formación"
            
        elif any(k in url_lower for k in ["legal", "derecho", "abogado", "law", "juridico"]):
            categoria = "Legal"
        self.datos_recopilados.append({
            "URL": url,
            "Titulo": titulo,
            "Precio": precio,
            "Categoria": categoria,
            "Texto": texto_pagina
        })

    def _agregar_enlaces(self, enlaces: list[str]) -> None:
        for url in enlaces:
            if url not in self.visitadas and url not in self.pendientes:
                self.pendientes.append(url)

    def recorrer(self, max_paginas: int = MAX_PAGINAS_DEFAULT) -> pd.DataFrame:
        paginas_visitadas = 0

        print(f"\nIniciando crawler desde: {self.url_principal}")
        print(f"Límite de páginas: {max_paginas}\n")

        while self.pendientes and paginas_visitadas < max_paginas:
            url = self.pendientes.popleft()

            if url in self.visitadas:
                continue

            self.visitadas.add(url)
            paginas_visitadas += 1
            print(f"[{paginas_visitadas}/{max_paginas}] Visitando: {url}")

            try:
                respuesta = requests.get(url, headers=HEADERS, timeout=15)

                if respuesta.status_code != 200:
                    print(f"[ERROR] Código HTTP {respuesta.status_code}: {url}")
                    continue

                soup = BeautifulSoup(respuesta.text, "html.parser")
                
                self._extraer_datos_pagina(soup, url)
                
                enlaces = self._extraer_enlaces_internos(soup, url)
                self._agregar_enlaces(enlaces)
                
                time.sleep(1)

            except requests.exceptions.RequestException as error:
                print(f"[ERROR] {url}: {error}")

        print(f"\nCrawler finalizado. Páginas visitadas: {len(self.visitadas)}")
        return pd.DataFrame(self.datos_recopilados)


def mineria_de_datos(df: pd.DataFrame) -> None:
    print("\n" + "=" * 40)
    print("RESULTADOS DE MINERÍA DE DATOS")
    print("=" * 40)

    if df.empty:
        print("El DataFrame está vacío. No hay datos para analizar.")
        return

    df_precios = df.dropna(subset=['Precio'])

    if not df_precios.empty:
        precio_promedio = df_precios['Precio'].mean()
        precio_minimo = df_precios['Precio'].min()
        precio_maximo = df_precios['Precio'].max()
        
        print("\n--- ANÁLISIS DE SALARIOS ---")
        print(f"Salario promedio : ${precio_promedio:,.2f}")
        print(f"Salario mínimo   : ${precio_minimo:,.2f}")
        print(f"Salario máximo   : ${precio_maximo:,.2f}")
    else:
        print("\n[!] No se encontraron precios válidos en el formato esperado.")

    print("\n--- PALABRAS MÁS FRECUENTES (TÍTULOS) ---")
    
    texto_titulos = " ".join(df['Titulo'].astype(str)).lower()
    palabras = re.findall(r'\b[a-záéíóúñ]{4,}\b', texto_titulos)
    contador_palabras = Counter(palabras)
    for palabra, frec in contador_palabras.most_common(5):
        print(f" • {palabra.capitalize()}: {frec} repeticiones")

    print("\n--- CATEGORÍAS PREDOMINANTES ---")
    frecuencia_categorias = df['Categoria'].value_counts()
    for categoria, cantidad in frecuencia_categorias.items():
        porcentaje = (cantidad / len(df)) * 100
        print(f" • {categoria}: {cantidad} ({porcentaje:.1f}%)")

    print("\n--- TENDENCIAS (SALARIO POR CATEGORÍA) ---")
    if not df_precios.empty:
        tendencias = df_precios.groupby('Categoria')['Precio'].mean().sort_values(ascending=False)
        for categoria, promedio in tendencias.items():
            print(f" • {categoria}: ${promedio:,.2f} en promedio")
    else:
        print(" • No hay suficientes datos de precios para marcar tendencias.")


def main() -> None:
    print("=" * 60)
    print("PROYECTO 3 - Crawler Automático y Minería de Datos")
    print("=" * 60)

    url = input("\nIngrese la URL principal: ").strip()
    if not url:
        print("Debe ingresar una URL válida.")
        return

    max_paginas = input(f"Máximo de páginas (default {MAX_PAGINAS_DEFAULT}): ").strip()
    limite = int(max_paginas) if max_paginas.isdigit() else MAX_PAGINAS_DEFAULT

    crawler = CrawlerEmpleo(url)
    df_datos = crawler.recorrer(max_paginas=limite)

    #Guarda el DataFrame en un archivo CSV físico
    archivo_csv = "datos_extraidos.csv"
    df_datos.to_csv(archivo_csv, index=False, encoding='utf-8')
    print(f"\n Datos guardados exitosamente en '{archivo_csv}'")

    mineria_de_datos(df_datos)


if __name__ == "__main__":
    main()