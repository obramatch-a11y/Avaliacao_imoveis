import asyncio
import json
import os
import re
from urllib.parse import quote, quote_plus
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
        self.debug: dict = {"urls": [], "parser": [], "amostra_bruta": [], "trecho_html": ""}

    ALUGUEL_RE = re.compile(
        r"\b(aluga-?se|alugo|aluguel|alugar|para alugar|loca[cç][aã]o|locar)\b", re.IGNORECASE
    )
    VENDA_RE = re.compile(
        r"\b(vende-?se|vendo|venda|[àa] venda|para vender|financi\w+)\b", re.IGNORECASE
    )

    def _bate_finalidade(self, item: dict, finalidade: str) -> bool:
        """Descarta anúncios cujo texto indica a finalidade oposta à escolhida."""
        texto = f"{item.get('titulo', '')} {item.get('descricao', '')}"
        tem_aluguel = bool(self.ALUGUEL_RE.search(texto))
        tem_venda = bool(self.VENDA_RE.search(texto))
        if finalidade == "VENDA":
            return not (tem_aluguel and not tem_venda)
        return not (tem_venda and not tem_aluguel)

    @staticmethod
    def _slug(texto: str) -> str:
        t = remover_acentos(texto or "").lower().strip()
        return re.sub(r"[^a-z0-9]+", "-", t).strip("-")

    def _montar_url(self, params: BuscaImovelInput, pagina: int, modo: str = "caminho") -> str:
        uf = params.uf.lower().strip()
        tipo = self.TIPO_SLUGS.get(params.tipo_imovel, "apartamentos")
        fin = self.FINALIDADE_SLUGS.get(params.finalidade, "venda")
        base = f"https://www.olx.com.br/imoveis/{fin}/{tipo}/estado-{uf}"

        if modo == "caminho":
            # Cidade (e bairro) no caminho, como o próprio OLX faz
            url = f"{base}/{self._slug(params.cidade)}"
            if params.bairro:
                url += f"/{self._slug(params.bairro)}"
            url += f"?o={pagina}"
        else:
            termo_busca = f"{params.cidade} {params.bairro or ''}".strip()
            url = f"{base}?q={quote_plus(remover_acentos(termo_busca))}&o={pagina}"

        if params.area_min:
            url += f"&ss={int(params.area_min)}"
        if params.area_max:
            url += f"&se={int(params.area_max)}"
        if params.quartos_min:
            url += f"&ros={int(params.quartos_min)}"
        return url

    def _texto_item(self, item: dict) -> str:
        return f"{item.get('titulo', '')} {item.get('detalhes', '')} {item.get('descricao', '')}"

    def _inferir_local(self, item: dict, params: BuscaImovelInput) -> None:
        """Lê 'Cidade, Bairro' do texto do cartão quando o OLX não traz o bairro."""
        if item.get("bairro"):
            return
        texto = self._texto_item(item)
        m = re.search(
            rf"{re.escape(params.cidade)}\s*,\s*([^,\d|•\n]+?)(?=\s+(?:Hoje|Ontem|\d{{1,2}}\s+de\s|\d{{1,2}}:\d{{2}}|R\$)|\s{{2,}}|$)",
            texto,
            re.IGNORECASE,
        )
        if m:
            item["bairro"] = m.group(1).strip()
            item.setdefault("cidade", params.cidade)

    def _local_confere(self, item: dict, params: BuscaImovelInput) -> bool:
        """Descarta anúncios de outra cidade/bairro quando o OLX informa o local."""
        cidade = self._slug(item.get("cidade", ""))
        if cidade and cidade != self._slug(params.cidade):
            return False
        bairro = self._slug(item.get("bairro", ""))
        if params.bairro and bairro and bairro != self._slug(params.bairro):
            return False
        return True

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
                        "cidade": ad.get("locationDetails", {}).get("municipality", ""),
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
        proxy_url = "".join((os.getenv("OLX_PROXY_URL") or "").split()) or None
        verificar_ssl = os.getenv("OLX_PROXY_VERIFY_SSL", "true").lower() != "false"
        # API de scraping opcional: modelo de URL com {url}, ex.:
        # https://api.scrapingant.com/v2/general?url={url}&x-api-key=CHAVE&proxy_country=BR
        modelo_api = "".join((os.getenv("OLX_FETCH_TEMPLATE") or "").split()) or None
        if not proxy_url and not modelo_api:
            self.diagnostico.append(
                "Sem proxy/API configurado (OLX_FETCH_TEMPLATE ou OLX_PROXY_URL): "
                "o OLX costuma bloquear servidores em nuvem."
            )

        async with httpx.AsyncClient(
            headers=self.HEADERS,
            timeout=90.0 if (proxy_url or modelo_api) else 20.0,
            follow_redirects=True,
            proxy=proxy_url,
            verify=verificar_ssl,
        ) as client:
            modo = "caminho"
            pagina = 1
            while pagina <= params.limite_paginas:
                url = self._montar_url(params, pagina, modo)
                try:
                    alvo = modelo_api.replace("{url}", quote(url, safe="")) if modelo_api else url
                    resp = await client.get(alvo)
                    itens: list[dict] = []
                    self.debug["urls"].append(url)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "lxml")
                        itens = self._extrair_de_next_data(soup)
                        parser = "next_data"
                        if not itens:
                            itens = self._extrair_de_html_cards(soup)
                            parser = "html_cards"
                        self.debug["parser"].append(f"pagina {pagina}: {parser} ({len(itens)} itens)")
                        if not self.debug["amostra_bruta"]:
                            self.debug["amostra_bruta"] = itens[:3]
                            self.debug["trecho_html"] = resp.text[:1500]
                    else:
                        self.diagnostico.append(f"Página {pagina}: OLX respondeu HTTP {resp.status_code}")

                    if not itens:
                        if pagina == 1 and modo == "caminho":
                            modo = "texto"  # tenta de novo com busca por texto
                            continue
                        if resp.status_code == 200:
                            self.diagnostico.append(
                                f"Página {pagina}: HTTP 200, mas nenhum anúncio encontrado ({len(resp.text)} bytes)"
                            )
                        break

                    for i in itens:
                        self._inferir_local(i, params)
                    antes = len(itens)
                    itens = [
                        i for i in itens
                        if self._bate_finalidade(i, params.finalidade) and self._local_confere(i, params)
                    ]
                    if antes != len(itens):
                        self.diagnostico.append(
                            f"Página {pagina}: {antes - len(itens)} anúncio(s) descartado(s) "
                            f"(finalidade ou local diferente do pedido)"
                        )

                    for item in itens:
                        link = item.get("url", "")
                        if link and link in urls_vistas:
                            continue
                        if link:
                            urls_vistas.add(link)
                        coletados.append(item)

                    pagina += 1
                    await asyncio.sleep(1.5)
                except Exception as exc:
                    self.diagnostico.append(f"Página {pagina}: erro {type(exc).__name__}: {exc}")
                    break

        if params.bairro and coletados:
            alvo_b = self._slug(params.bairro)
            do_bairro = [
                i for i in coletados
                if alvo_b in self._slug(i.get("bairro", "")) or alvo_b in self._slug(self._texto_item(i))
            ]
            if do_bairro:
                for i in do_bairro:
                    if not i.get("bairro"):
                        i["bairro"] = params.bairro
                if len(do_bairro) != len(coletados):
                    self.diagnostico.append(
                        f"{len(coletados) - len(do_bairro)} anúncio(s) descartado(s) por não serem do bairro {params.bairro}"
                    )
                coletados = do_bairro
            else:
                self.diagnostico.append(
                    f"Não foi possível confirmar o bairro {params.bairro} nos anúncios; mantidos todos da cidade."
                )

        return coletados
