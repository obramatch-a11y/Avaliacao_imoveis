import asyncio
import json
import os
import re
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup
from app.models import BuscaImovelInput
from app.normalizer import remover_acentos
from app.scrapers.base import BaseScraper


class OLXScraper(BaseScraper):
    nome_fonte = "OLX"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    TIPO_SLUGS = {
        "APARTAMENTO": "apartamentos",
        "CASA": "casas",
        "TERRENO": "terrenos",
        "COMERCIAL": "comercio-e-industria",
    }

    FINALIDADE_SLUGS = {
        "VENDA": "venda",
        "LOCACAO": "aluguel",
    }

    def __init__(self):
        self.diagnostico: list[str] = []

    def _montar_url(self, params: BuscaImovelInput, pagina: int) -> str:
        uf = params.uf.lower().strip()
        tipo = self.TIPO_SLUGS.get(params.tipo_imovel, "apartamentos")
        fin = self.FINALIDADE_SLUGS.get(params.finalidade, "venda")

        termo_busca = f"{params.cidade} {params.bairro or ''}".strip()
        q = quote_plus(remover_acentos(termo_busca))

        url = f"https://www.olx.com.br/imoveis/{fin}/{tipo}/estado-{uf}?q={q}&o={pagina}"
        if params.area_min:
            url += f"&ss={int(params.area_min)}"
        if params.area_max:
            url += f"&se={int(params.area_max)}"
        if params.quartos_min:
            url += f"&ros={int(params.quartos_min)}"
        return url

    def _extrair_de_next_data(self, soup: BeautifulSoup) -> list[dict]:
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return []

        resultados = []
        try:
            data = json.loads(script.string)
            props = data.get("props", {}).get("pageProps", {})
            ads = props.get("ads", []) or props.get("initialData", {}).get("ads", [])

            for ad in ads:
                if not isinstance(ad, dict) or not ad.get("subject"):
                    continue
                propriedades = {
                    p.get("name", "").lower(): p.get("value", "")
                    for p in ad.get("properties", [])
                    if isinstance(p, dict)
                }
                resultados.append(
                    {
                        "fonte": self.nome_fonte,
                        "titulo": ad.get("subject", ""),
                        "preco": ad.get("price", ""),
                        "bairro": ad.get("locationDetails", {}).get("neighbourhood", ""),
                        "area": propriedades.get("size", ""),
                        "quartos": propriedades.get("rooms", ""),
                        "banheiros": propriedades.get("bathrooms", ""),
                        "vagas": propriedades.get("garage_spaces", ""),
                        "condominio": propriedades.get("condominio", ""),
                        "iptu": propriedades.get("iptu", ""),
                        "detalhes": " ".join(f"{k}:{v}" for k, v in propriedades.items()),
                        "descricao": ad.get("body", ""),
                        "url": ad.get("url", ""),
                    }
                )
        except Exception:
            return []
        return resultados

    def _extrair_de_html_cards(self, soup: BeautifulSoup) -> list[dict]:
        resultados = []
        cards = soup.select("section.olx-adcard, li[data-lurker-detail='list_id']")
        for card in cards:
            link_tag = card.find("a", href=True)
            titulo_tag = card.find(["h2", "h3"])
            texto_card = card.get_text(" ", strip=True)

            preco_match = re.search(r"R\$\s*[\d.,]+", texto_card)
            area_match = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", texto_card)
            quartos_match = re.search(r"(\d+)\s*quarto", texto_card, re.IGNORECASE)
            vagas_match = re.search(r"(\d+)\s*vaga", texto_card, re.IGNORECASE)
            banheiros_match = re.search(r"(\d+)\s*banheiro", texto_card, re.IGNORECASE)

            if not titulo_tag and not preco_match:
                continue

            resultados.append(
                {
                    "fonte": self.nome_fonte,
                    "titulo": titulo_tag.get_text(strip=True) if titulo_tag else "Anúncio OLX",
                    "preco": preco_match.group(0) if preco_match else "",
                    "bairro": "",
                    "area": area_match.group(1) if area_match else "",
                    "quartos": quartos_match.group(1) if quartos_match else "",
                    "banheiros": banheiros_match.group(1) if banheiros_match else "",
                    "vagas": vagas_match.group(1) if vagas_match else "",
                    "condominio": "",
                    "iptu": "",
                    "detalhes": texto_card,
                    "descricao": "",
                    "url": link_tag["href"] if link_tag else "",
                }
            )
        return resultados

    async def buscar(self, params: BuscaImovelInput) -> list[dict]:
        coletados: list[dict] = []
        urls_vistas: set[str] = set()

        # Proxy residencial opcional (ex.: http://usuario:senha@host:porta), definido no Render
        proxy_url = os.getenv("OLX_PROXY_URL") or None
        verificar_ssl = os.getenv("OLX_PROXY_VERIFY_SSL", "true").lower() != "false"
        if not proxy_url:
            self.diagnostico.append(
                "Sem proxy configurado (OLX_PROXY_URL): o OLX costuma bloquear servidores em nuvem."
            )

        async with httpx.AsyncClient(
            headers=self.HEADERS,
            timeout=60.0 if proxy_url else 20.0,
            follow_redirects=True,
            proxy=proxy_url,
            verify=verificar_ssl,
        ) as client:
            for pagina in range(1, params.limite_paginas + 1):
                url = self._montar_url(params, pagina)
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        self.diagnostico.append(f"Página {pagina}: OLX respondeu HTTP {resp.status_code}")
                        break
                    soup = BeautifulSoup(resp.text, "lxml")
                    itens = self._extrair_de_next_data(soup)
                    if not itens:
                        itens = self._extrair_de_html_cards(soup)

                    if not itens:
                        self.diagnostico.append(
                            f"Página {pagina}: HTTP 200, mas nenhum anúncio encontrado no HTML ({len(resp.text)} bytes)"
                        )
                        break

                    for item in itens:
                        link = item.get("url", "")
                        if link and link in urls_vistas:
                            continue
                        if link:
                            urls_vistas.add(link)
                        coletados.append(item)

                    await asyncio.sleep(1.5)
                except Exception as exc:
                    self.diagnostico.append(f"Página {pagina}: erro {type(exc).__name__}: {exc}")
                    break

        return coletados
