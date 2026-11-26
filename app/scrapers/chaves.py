import re
from bs4 import BeautifulSoup
from app.fotos import fotos_de_tag
from app.models import BuscaImovelInput
from app.scrapers.olx import OLXScraper


class ChavesNaMaoScraper(OLXScraper):
    """Chaves na Mão: reaproveita o canal de acesso (proxy/API) e os filtros do coletor principal.
    O preço, o bairro e os quartos vêm do endereço do anúncio, que é estável e público."""

    nome_fonte = "Chaves na Mão"
    TIPOS = {"APARTAMENTO": "apartamentos", "CASA": "casas", "TERRENO": "terrenos", "COMERCIAL": "imoveis-comerciais"}
    FIN = {"VENDA": "a-venda", "LOCACAO": "para-alugar"}

    def _montar_url(self, params: BuscaImovelInput, pagina: int, modo: str = "caminho") -> str:
        self._params = params
        tipo = self.TIPOS.get(params.tipo_imovel, "apartamentos")
        fin = self.FIN.get(params.finalidade, "a-venda")
        url = f"https://www.chavesnamao.com.br/{tipo}-{fin}/{params.uf.lower()}-{self._slug(params.cidade)}/"
        return url + (f"?pg={pagina}" if pagina > 1 else "")

    def _extrair_de_next_data(self, soup: BeautifulSoup) -> list[dict]:
        return []

    def _extrair_de_html_cards(self, soup: BeautifulSoup) -> list[dict]:
        p = getattr(self, "_params", None)
        prefixo = f"{p.uf.lower()}-{self._slug(p.cidade)}" if p else ""
        itens, vistos = [], set()
        for a in soup.select("a[href*='/imovel/']"):
            href = a["href"]
            if href.startswith("/"):
                href = "https://www.chavesnamao.com.br" + href
            if href in vistos:
                continue
            vistos.add(href)
            slug = href.split("/imovel/")[1].split("/")[0]
            preco = re.search(r"RS(\d+)", slug)
            if not preco:
                continue
            texto = a.get_text(" ", strip=True)
            bairro = ""
            m = re.search(rf"{re.escape(prefixo)}-(.+?)-RS\d+", slug) if prefixo else None
            if m:
                bairro = m.group(1).replace("-", " ").title()
            q = re.search(r"(\d+)-quartos?", slug)
            area = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", texto)
            ban = re.search(r"(\d+)\s*banheiro", texto, re.IGNORECASE)
            vag = re.search(r"(\d+)\s*vaga", texto, re.IGNORECASE)
            itens.append(
                {
                    "fonte": self.nome_fonte,
                    "titulo": (a.get("title") or texto)[:140],
                    "preco": f"R$ {int(preco.group(1)):,}".replace(",", "."),
                    "cidade": p.cidade if (p and prefixo and prefixo in slug) else "",
                    "bairro": bairro,
                    "area": area.group(1) if area else "",
                    "quartos": q.group(1) if q else "",
                    "banheiros": ban.group(1) if ban else "",
                    "vagas": vag.group(1) if vag else "",
                    "condominio": "",
                    "iptu": "",
                    "detalhes": texto,
                    "descricao": "",
                    "url": href,
                    "fotos": fotos_de_tag(a),
                }
            )
        return itens
