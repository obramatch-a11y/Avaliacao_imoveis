"""Testes do diagnóstico de fontes. Usam respostas sintéticas (MockTransport) só para provar a lógica de
classificação e de leitura; não representam dados reais de nenhuma fonte."""
import asyncio

import httpx

from app.diag_fontes import (
    BLOQUEIO, ERRO_EXTRACAO, FALHA_CONEXAO, NAO_EXECUTADO, OK, ROBOTS_PROIBE, SEM_ANUNCIOS,
    classificar, diagnosticar_fontes, interpretar_robots, ler_estruturados, ler_markdown_chaves, robots_permite,
)
from app.models import BuscaImovelInput

ROBOTS_CHAVES = """User-agent: *
Disallow: /*?*
Disallow: /api/
Allow: /api/mcp
Allow: /.well-known/
Disallow: /imoveis/integracao/
Sitemap: https://www.chavesnamao.com.br/sitemap-2026-realty-ads-index.xml

User-agent: wget
Disallow: /
"""

MD = """# Resultado
16.524 anúncios encontrados; mostrando 2.

---
## Apartamento no Centro
- URL: https://www.chavesnamao.com.br/imovel/apartamento-a-venda-pe-recife-centro-id-1
- Preço: R$ 350.000
- Local: Boa Viagem, Recife - PE
- Tipo: Apartamento
- Características: 3 quartos, 2 vagas, 85 m²

---
## Casa
- URL: https://www.chavesnamao.com.br/imovel/casa-a-venda-pe-recife-id-2
- Preço: R$ 900.000
- Local: Casa Forte, Recife - PE
- Características: 4 quartos, 220 m²
"""


def _params():
    return BuscaImovelInput(uf="PE", cidade="Recife", bairro="", finalidade="VENDA", tipo_imovel="APARTAMENTO", limite_paginas=1)  # type: ignore


def test_classificar_separa_as_causas():
    assert classificar(None, "ConnectTimeout", [], 0) == FALHA_CONEXAO
    assert classificar(403, None, [], 0) == BLOQUEIO
    assert classificar(429, None, [], 0) == BLOQUEIO
    assert classificar(200, None, ["cloudflare"], 0, conteudo_ok=False) == BLOQUEIO
    assert classificar(200, None, [], 0, total_declarado=0) == SEM_ANUNCIOS
    assert classificar(200, None, [], 0, total_declarado=None) == ERRO_EXTRACAO
    assert classificar(200, None, [], 12) == OK
    assert classificar(404, None, [], 0) == "ERRO_HTTP"


def test_robots_usa_caminho_mais_especifico_e_curingas():
    r = interpretar_robots(ROBOTS_CHAVES)["regras"]
    assert robots_permite(r, "/.well-known/search?q=casa+recife") is True   # Allow mais específico vence o Disallow /*?*
    assert robots_permite(r, "/imovel/apartamento-1") is True
    assert robots_permite(r, "/imoveis/integracao/x") is False
    assert robots_permite(r, "/api/foo") is False
    assert robots_permite(r, "/api/mcp") is True
    assert robots_permite(r, "/apartamentos-a-venda/pe-recife/?pg=2") is False


def test_robots_agente_bloqueado_nominalmente_usa_o_grupo_dele():
    r = interpretar_robots("User-agent: inferenciaestatistica-diagnostico\nDisallow: /\n\nUser-agent: *\nAllow: /")["regras"]
    assert robots_permite(r, "/qualquer") is False


def test_ler_markdown_chaves():
    d = ler_markdown_chaves(MD)
    assert d["total_declarado"] == 16524
    assert len(d["itens"]) == 2
    a = d["itens"][0]
    assert a["preco"] == "R$ 350.000" and a["area_m2"] == "85" and a["quartos"] == "3" and a["bairro"] == "Boa Viagem"
    assert d["itens"][1]["tipo"] == ""  # campo ausente fica vazio, sem inventar


def test_ler_estruturados_jsonld_e_og():
    html = """<html><head><title>Anúncio</title>
    <meta property="og:image" content="https://x/y.jpg">
    <script type="application/ld+json">{"@graph":[{"@type":"Product","name":"Ap","image":["a","b"],
    "offers":{"price":"1"}},{"@type":"BreadcrumbList"}]}</script></head><body></body></html>"""
    e = ler_estruturados(html)
    assert e["json_ld_blocos"] == 3 and "Product" in e["tipos_schema_org"]
    assert e["imagens_no_json_ld"] == 2 and e["og_image"] == 1 and "offers" in e["campos_no_json_ld"]
    assert e["next_data"] is False


def _transporte(modo):
    def h(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if modo == "queda":
            raise httpx.ConnectError("sem rota")
        if u.endswith("/robots.txt"):
            if "olx.com.br" in u:
                return httpx.Response(403, text="blocked")
            return httpx.Response(200, text=ROBOTS_CHAVES)
        if ".well-known/search" in u:
            return httpx.Response(200, text=MD, headers={"content-type": "text/markdown"})
        if "sitemap-2026-realty-ads-index" in u:
            return httpx.Response(200, text="<sitemapindex><sitemap><loc>https://www.chavesnamao.com.br/s1.xml</loc></sitemap></sitemapindex>")
        if u.endswith("/s1.xml"):
            return httpx.Response(200, text="<urlset><url><loc>https://www.chavesnamao.com.br/imovel/a-1</loc></url></urlset>")
        if "/imovel/" in u:
            return httpx.Response(200, text='<html><script type="application/ld+json">{"@type":"Product","name":"x"}</script></html>')
        if "olx.com.br" in u:
            return httpx.Response(403, text="Sorry, you have been blocked cloudflare")
        return httpx.Response(404)
    return httpx.MockTransport(h)


def test_diagnostico_completo_com_respostas_sinteticas():
    r = asyncio.run(diagnosticar_fontes(_params(), _transporte("ok")))
    f = r["fontes"]
    assert f["chaves_busca_oficial"]["classificacao"] == OK
    assert f["chaves_busca_oficial"]["total_declarado"] == 16524
    assert f["chaves_busca_oficial"]["tem_foto_no_retorno"] is False
    assert f["chaves_sitemap"]["classificacao"] == OK
    assert f["chaves_sitemap"]["primeiro_sitemap_filho"]["urls_de_anuncio"] == 1
    assert f["chaves_pagina_anuncio"]["classificacao"] == OK
    # robots do OLX respondeu 403 (4xx: sem restrições pelo RFC 9309), a página respondeu 403: bloqueio de acesso
    assert f["olx_listagem"]["classificacao"] == BLOQUEIO
    assert "memoria_processo_fim_mb" in r["ambiente"] and r["ambiente"]["sem_proxy"] is True
    assert "_urls" not in f["chaves_busca_oficial"]


def test_diagnostico_com_queda_de_rede_nao_vira_bloqueio():
    r = asyncio.run(diagnosticar_fontes(_params(), _transporte("queda")))
    assert r["fontes"]["chaves_busca_oficial"]["classificacao"] == FALHA_CONEXAO
    assert r["fontes"]["olx_listagem"]["classificacao"] == FALHA_CONEXAO
    # robots inacessível por falha de rede => não acessa (RFC 9309) e nada é classificado como bloqueio
    assert BLOQUEIO not in r["resumo"].values()
    assert r["fontes"]["chaves_pagina_anuncio"]["classificacao"] == NAO_EXECUTADO
