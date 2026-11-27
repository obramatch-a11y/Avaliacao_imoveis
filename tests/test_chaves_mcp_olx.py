"""Testes da integração MCP do Chaves na Mão (respostas SINTÉTICAS, só para provar a lógica) e do extrator da OLX
(páginas reais salvas pelo projeto olx-brazil-scraper, MIT, em tests/fixtures)."""
import asyncio
import json
import pathlib

import httpx

from app.models import BuscaImovelInput
from app.scrapers import chaves_mcp
from app.scrapers.chaves_mcp import ChavesNaMaoMCPScraper, filtros_do_pedido, itens_do_resultado
from app.scrapers.olx import OLXScraper

FIX = pathlib.Path(__file__).parent / "fixtures"


def _p(**kw):
    base = dict(uf="PE", cidade="Recife", bairro="", finalidade="VENDA", tipo_imovel="APARTAMENTO", limite_paginas=2)
    base.update(kw)
    return BuscaImovelInput(**base)  # type: ignore


def test_filtros_seguem_o_esquema_documentado():
    f = filtros_do_pedido(_p(finalidade="LOCACAO", bairro="Boa Viagem", preco_min=1000, preco_max=3000, area_min=50))
    assert f == {"transaction": "aluguel", "propertyType": "apartamento", "city": "Recife", "state": "PE",
                 "neighborhood": "Boa Viagem", "minPrice": 1000, "maxPrice": 3000, "minArea": 50.0}


def test_resultado_structured_content_json_e_markdown():
    estruturado = {"structuredContent": {"total": 120, "results": [
        {"title": "Apto 2q", "price": 350000, "location": {"neighborhood": "Boa Viagem", "city": "Recife"},
         "bedrooms": 2, "parkingSpots": 1, "area": 60, "url": "https://x/imovel/a-1", "images": ["https://x/f.jpg"]}]}}
    it, total, fmt = itens_do_resultado(estruturado)
    assert fmt == "structuredContent" and total == 120 and len(it) == 1
    assert it[0]["bairro"] == "Boa Viagem" and it[0]["area"] == "60.0" and it[0]["vagas"] == "1" and it[0]["fotos"] == ["https://x/f.jpg"]
    assert it[0]["preco"] == "R$ 350.000"
    em_texto = {"content": [{"type": "text", "text": json.dumps({"items": [{"titulo": "Casa", "preco": "R$ 900.000", "link": "https://x/imovel/c-2"}]})}]}
    it2, _, fmt2 = itens_do_resultado(em_texto)
    assert fmt2 == "json_em_texto" and it2[0]["url"] == "https://x/imovel/c-2"
    md = {"content": [{"type": "text", "text": "2 anúncios encontrados; mostrando 1.\n\n---\n## Casa\n- URL: https://x/imovel/c-3\n- Preço: R$ 500.000\n- Local: Centro, Recife - PE\n- Características: 3 quartos, 100 m²\n"}]}
    it3, total3, fmt3 = itens_do_resultado(md)
    assert fmt3 == "markdown" and total3 == 2 and it3[0]["quartos"] == "3"
    assert itens_do_resultado({"content": [{"type": "text", "text": "nada reconhecível"}]})[2] == "nao_reconhecido"


def test_formato_real_observado_no_render():
    r = {"structuredContent": {"resultados": [{"id": "45024961", "title": "Lindo apartamento", "url": "https://www.chavesnamao.com.br/imovel/x/id-45024961/",
         "transaction": "venda", "propertyType": "Apartamento", "priceBRL": 700000, "location": {"city": "Recife", "state": "PE", "neighborhood": "Boa Viagem"},
         "bedrooms": 3, "bathrooms": 3, "parkingSpots": 1, "areaM2": 98, "imageUrl": "1374104/45024961/pe-recife-a-6a639ec0-1.jpg"}]}}
    it, _, fmt = itens_do_resultado(r)
    assert fmt == "structuredContent" and it[0]["preco"] == "R$ 700.000" and it[0]["area"] == "98.0"
    assert it[0]["fotos"] == ["https://www.chavesnamao.com.br/imn/0640x0450/N/40/imoveis/1374104/45024961/pe-recife-a-6a639ec0-1.jpg"]


def _servidor(modo="json", falha=None):
    chamadas = []

    def h(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if "well-known/search" in u:
            if falha == "busca":
                return httpx.Response(500)
            return httpx.Response(200, text="1 anúncios encontrados; mostrando 1.\n\n---\n## Ap\n- URL: https://www.chavesnamao.com.br/imovel/z-9\n- Preço: R$ 200.000\n- Local: Várzea, Recife\n- Características: 2 quartos, 50 m²\n")
        if "api/mcp" not in u:
            return httpx.Response(404)
        if falha == "mcp_fora":
            return httpx.Response(503, text="manutenção")
        corpo = json.loads(req.content)
        chamadas.append(corpo.get("method"))
        if "id" not in corpo:
            return httpx.Response(202)
        if corpo["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": corpo["id"], "result": {"protocolVersion": "2025-03-26", "serverInfo": {"name": "chaves"}}},
                                  headers={"mcp-session-id": "S1"})
        if not corpo["params"]["arguments"].get("query"):
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": corpo["id"], "error": {"code": -32602, "message": "Ferramenta inválida argumentos"}})
        pagina = corpo["params"]["arguments"].get("page", 1)
        itens = [{"title": f"Apto {pagina}-{i}", "price": 300000 + i, "location": {"neighborhood": "Boa Viagem", "city": "Recife"},
                  "bedrooms": 2, "area": 60, "url": f"https://www.chavesnamao.com.br/imovel/p{pagina}-{i}"} for i in range(15 if pagina == 1 else 3)]
        res = {"content": [{"type": "text", "text": json.dumps({"total": 18, "results": itens})}]}
        msg = {"jsonrpc": "2.0", "id": corpo["id"], "result": res}
        if modo == "sse":
            return httpx.Response(200, text=f"event: message\ndata: {json.dumps(msg)}\n\n", headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=msg)
    return httpx.MockTransport(h), chamadas


def _rodar(sc, params, transporte):
    orig = httpx.AsyncClient

    class Cli(orig):
        def __init__(self, *a, **k):
            k["transport"] = transporte
            super().__init__(*a, **k)

    httpx.AsyncClient = Cli  # type: ignore
    chaves_mcp.httpx.AsyncClient = Cli  # type: ignore
    real_sleep = asyncio.sleep

    async def sem_espera(*_a, **_k):
        await real_sleep(0)

    chaves_mcp.asyncio.sleep = sem_espera  # type: ignore
    try:
        async def go():
            return await sc.buscar(params)
        return asyncio.run(go())
    finally:
        chaves_mcp.asyncio.sleep = real_sleep  # type: ignore
        httpx.AsyncClient = orig  # type: ignore
        chaves_mcp.httpx.AsyncClient = orig  # type: ignore


def test_scraper_mcp_json_pagina_e_usa_sessao():
    t, chamadas = _servidor("json")
    sc = ChavesNaMaoMCPScraper()
    r = _rodar(sc, _p(limite_paginas=3), t)
    assert sc.canal_usado == "mcp" and len(r) == 18 and sc.total_declarado == 18
    assert chamadas[:2] == ["initialize", "notifications/initialized"] and chamadas.count("tools/call") == 2  # página 2 veio incompleta
    assert r[0]["fonte"] == "Chaves na Mão"


def test_scraper_mcp_sse():
    t, _ = _servidor("sse")
    sc = ChavesNaMaoMCPScraper()
    r = _rodar(sc, _p(limite_paginas=1), t)
    assert sc.canal_usado == "mcp" and len(r) == 15


def test_cai_para_busca_oficial_quando_mcp_cai():
    t, _ = _servidor(falha="mcp_fora")
    sc = ChavesNaMaoMCPScraper()
    r = _rodar(sc, _p(), t)
    assert sc.canal_usado == "well-known/search" and len(r) == 1 and any("MCP oficial indisponível" in d for d in sc.diagnostico)


def test_olx_extrator_flight_com_pagina_real_salva():
    html = (FIX / "olx_listing_realestate_rj.html").read_text(encoding="utf-8")
    itens = OLXScraper()._extrair_de_flight(html)
    assert len(itens) == 50
    i = itens[0]
    assert i["preco"] == "R$ 457.300" and i["area"] == "200m²" and i["quartos"] == "4" and i["banheiros"] == "2" and i["vagas"] == "2"
    assert i["bairro"] == "Parque João Maria" and i["cidade_origem"] == "Campos dos Goytacazes" and i["tipo_area"] == "Área construída"
    assert i["url"].startswith("https://rj.olx.com.br/") and i["fotos"] and "/thumbs700x500/" in i["fotos"][0]


def test_olx_listagem_vazia_e_html_sem_dados_caem_no_extrator_antigo():
    s = OLXScraper()
    assert s._extrair_de_flight((FIX / "olx_listing_empty.html").read_text(encoding="utf-8")) == []
    assert s._extrair_de_flight("<html>nada</html>") == []


def test_dedup_por_url_e_assinatura():
    from app.main import normalizar_lista
    base = {"fonte": "OLX", "titulo": "Ap", "preco": "R$ 300.000", "bairro": "Boa Viagem", "area": "60", "quartos": "2", "url": "https://a/1?x=1", "fotos": []}
    outro = dict(base, fonte="Chaves na Mão", url="https://b/9")           # mesma assinatura, outra fonte
    mesma_url = dict(base, preco="R$ 301.000", area="61")                    # mesma URL (sem query)
    sem_dados = {"fonte": "OLX", "titulo": "x", "preco": "", "bairro": "", "area": "", "url": "https://c/1"}
    sem_dados2 = dict(sem_dados, url="https://c/2")                           # sem área/preço: não deve fundir por assinatura
    r = normalizar_lista([base, outro, dict(mesma_url, url="https://a/1"), sem_dados, sem_dados2], _p())
    assert len(r) == 3


def test_interface_tem_todas_as_fontes_e_nao_exige_chave():
    html = (pathlib.Path(__file__).parent.parent / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'id="fonteTodas"' in html and 'value="olx"' in html and 'value="chaves"' in html
    assert "libere a importação primeiro" not in html
