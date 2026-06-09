import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque

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
    """Crawler automático para recorrer sitios web."""

    def __init__(self, url_principal: str):
        self.url_principal = normalizar_url(url_principal)
        self.dominio = urlparse(self.url_principal).netloc
        self.visitadas: set[str] = set()
        self.pendientes: deque[str] = deque([limpiar_url(self.url_principal)])

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

    def _agregar_enlaces(self, enlaces: list[str]) -> None:
        for url in enlaces:
            if url not in self.visitadas and url not in self.pendientes:
                self.pendientes.append(url)

    def recorrer(self, max_paginas: int = MAX_PAGINAS_DEFAULT) -> None:
        paginas_visitadas = 0

        print(f"\nIniciando crawler desde: {self.url_principal}")
        print(f"Límite de páginas: {max_paginas}\n")

        while self.pendientes and paginas_visitadas < max_paginas:
            url = self.pendientes.popleft()

            if url in self.visitadas:
                continue

            self.visitadas.add(url)
            paginas_visitadas += 1
            print(f"[OK] Visitando página: {url}")

            try:
                respuesta = requests.get(url, headers=HEADERS, timeout=15)

                if respuesta.status_code != 200:
                    print(f"[ERROR] Código HTTP {respuesta.status_code}: {url}")
                    continue

                soup = BeautifulSoup(respuesta.text, "html.parser")
                enlaces = self._extraer_enlaces_internos(soup, url)
                print(f"[OK] Enlaces encontrados: {len(enlaces)}")

                self._agregar_enlaces(enlaces)
                time.sleep(1)

            except requests.exceptions.Timeout:
                print(f"[ERROR] Tiempo de espera agotado: {url}")
            except requests.exceptions.ConnectionError:
                print(f"[ERROR] Error de conexión: {url}")
            except requests.exceptions.RequestException as error:
                print(f"[ERROR] {url}: {error}")

        print(f"\nCrawler finalizado. Páginas visitadas: {len(self.visitadas)}")


def main() -> None:
    print("=" * 60)
    print("PROYECTO 3 - Crawler Automático")
    print("=" * 60)

    url = input("\nIngrese la URL principal: ").strip()
    if not url:
        print("Debe ingresar una URL válida.")
        return

    max_paginas = input(f"Máximo de páginas (default {MAX_PAGINAS_DEFAULT}): ").strip()
    limite = int(max_paginas) if max_paginas.isdigit() else MAX_PAGINAS_DEFAULT

    crawler = CrawlerEmpleo(url)
    crawler.recorrer(max_paginas=limite)


if __name__ == "__main__":
    main()
