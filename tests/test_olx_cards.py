from bs4 import BeautifulSoup
from app.scrapers.olx import OLXScraper

CARD = """
<section class="olx-adcard"><a href="https://pe.olx.com.br/x-1"><h2>Alameda Mônica Campos | Piedade | 2 quartos | R$ 310 mil | Varanda e suíte</h2></a>
<span>52m²</span><span>2</span><span>2</span><span>1</span>
<span>R$ 310.000</span><span>IPTU R$ 1</span><span>Condomínio R$ 1</span>
<span>Jaboatão dos Guararapes, Piedade</span><span>Hoje, 18h50</span></section>
"""


def test_card_preco_nao_vem_do_titulo_e_icones_sao_lidos():
    item = OLXScraper()._extrair_de_html_cards(BeautifulSoup(CARD, "lxml"))[0]
    assert item["preco"] == "R$ 310.000"
    assert (item["area"], item["quartos"], item["banheiros"], item["vagas"]) == ("52", "2", "2", "1")
    assert item["iptu"] == "" and item["condominio"] == ""


def test_fotos_do_card_e_dominio_permitido():
    from app.fotos import fotos_de_anuncio, host_permitido
    html = CARD.replace("<span>52m²", '<img src="https://img.olx.com.br/images/1/a.jpg" srcset="https://img.olx.com.br/images/1/a.jpg 1x, https://img.olx.com.br/images/1/b.jpg 2x"><img src="https://evil.com/x.jpg"><img src="https://img.olx.com.br/logo.svg"><span>52m²')
    item = OLXScraper()._extrair_de_html_cards(BeautifulSoup(html, "lxml"))[0]
    assert item["fotos"] == ["https://img.olx.com.br/images/1/a.jpg", "https://img.olx.com.br/images/1/b.jpg"]
    assert not host_permitido("http://img.olx.com.br/a.jpg") and not host_permitido("https://olx.com.br.evil.com/a.jpg")
    pag = '<meta property="og:image" content="https://img.olx.com.br/images/9/z.jpg"><script type="application/ld+json">{"image":["https://img.olx.com.br/images/9/y.jpg"]}</script>'
    assert fotos_de_anuncio(pag) == ["https://img.olx.com.br/images/9/y.jpg", "https://img.olx.com.br/images/9/z.jpg"]


def test_coleta_assincrona_com_cancelamento(monkeypatch):
    import time
    from fastapi.testclient import TestClient
    import app.main as m

    async def falso_buscar(self, params, ao_progredir=None, cancelado=None):
        itens = []
        for pg in range(1, 4):
            if cancelado and cancelado():
                break
            itens.append({"fonte": "OLX", "titulo": f"Apto {pg}", "preco": f"R$ {300000 + pg}", "area": "50", "quartos": "2",
                          "bairro": "Piedade", "url": f"https://pe.olx.com.br/{pg}"})
            if ao_progredir:
                ao_progredir(pg, itens)
            import asyncio
            await asyncio.sleep(0.2)
        return itens

    monkeypatch.setattr(m.OLXScraper, "buscar", falso_buscar)
    with TestClient(m.app) as c:
        r = c.post("/coleta", data={"uf": "PE", "cidade": "Recife", "limite_paginas": 3, "fontes": "olx"})
        jid = r.json()["id"]
        time.sleep(0.3)
        c.post(f"/coleta/{jid}/cancelar")
        for _ in range(30):
            st = c.get(f"/coleta/{jid}").json()
            if st["estado"] != "rodando":
                break
            time.sleep(0.1)
        assert st["estado"] == "interrompida" and 1 <= st["encontrados"] < 3
        assert "Apto 1" in c.get(f"/coleta/{jid}/resultado").text


def test_chaves_na_mao_cartao():
    from app.models import BuscaImovelInput
    from app.scrapers.chaves import ChavesNaMaoScraper
    sc = ChavesNaMaoScraper()
    p = BuscaImovelInput(uf="PE", cidade="Jaboatão dos Guararapes", bairro="Piedade", finalidade="VENDA", tipo_imovel="APARTAMENTO")
    assert sc._montar_url(p, 2) == "https://www.chavesnamao.com.br/apartamentos-a-venda/pe-jaboatao-dos-guararapes/?pg=2"
    html = '<a href="/imovel/apartamento-a-venda-2-quartos-com-garagem-pe-jaboatao-dos-guararapes-piedade-RS450000/id-1/" title="Apto 2 quartos"><img src="https://images.chavesnamao.com.br/x.jpg">59 m² 2 banheiros 1 vaga</a>'
    it = sc._extrair_de_html_cards(BeautifulSoup(html, "lxml"))[0]
    assert (it["preco"], it["bairro"], it["quartos"], it["area"], it["vagas"]) == ("R$ 450.000", "Piedade", "2", "59", "1")
    assert it["fonte"] == "Chaves na Mão" and it["fotos"] == ["https://images.chavesnamao.com.br/x.jpg"]


def test_resultado_parcial_enquanto_coleta_roda(monkeypatch):
    import asyncio
    import time
    from fastapi.testclient import TestClient
    import app.main as m

    async def lento(self, params, ao_progredir=None, cancelado=None):
        itens = [{"fonte": "OLX", "titulo": "Apto A", "preco": "R$ 300.000", "area": "50", "quartos": "2", "bairro": "Piedade", "url": "https://pe.olx.com.br/a"}]
        ao_progredir(1, itens)
        for _ in range(40):
            if cancelado():
                break
            await asyncio.sleep(0.1)
        return itens

    monkeypatch.setattr(m.OLXScraper, "buscar", lento)
    with TestClient(m.app) as c:
        jid = c.post("/coleta", data={"uf": "PE", "cidade": "Recife", "fontes": "olx"}).json()["id"]
        time.sleep(0.3)
        html = c.get(f"/coleta/{jid}/resultado").text
        assert "Coleta em andamento" in html and "Apto A" in html
        c.post(f"/coleta/{jid}/cancelar")


def test_filtros_validados_no_backend_exemplos_do_relatorio():
    from app.main import normalizar_lista
    from app.models import BuscaImovelInput
    p = BuscaImovelInput(uf="PE", cidade="Recife", finalidade="VENDA", tipo_imovel="APARTAMENTO",
                         preco_min=200000, preco_max=600000, area_min=50, area_max=120)
    casos = [("R$ 2.900", "100"), ("R$ 75.000", "110"), ("R$ 578.000", "30"), ("R$ 1.600.000", "99"), ("R$ 2.400.000", "378"), ("R$ 450.000", "80")]
    brutos = [{"fonte": "OLX", "titulo": f"Apto {i}", "preco": pr, "area": ar, "quartos": "2", "bairro": "Boa Viagem", "url": f"https://x/{i}"} for i, (pr, ar) in enumerate(casos)]
    r = normalizar_lista(brutos, p)
    assert [a.fora_filtros for a in r] == [True, True, True, True, True, False]
    assert any("Área abaixo" in m for m in r[2].motivos) and any("Valor baixo demais" in m for m in r[0].motivos)
    assert r[5].motivos == [] and r[5].completude == 4


def test_correcoes_do_avaliador_na_exportacao():
    from app.main import aplicar_correcoes, normalizar_lista
    from app.models import BuscaImovelInput
    p = BuscaImovelInput(uf="PE", cidade="Recife", finalidade="VENDA", tipo_imovel="APARTAMENTO")
    r = normalizar_lista([{"fonte": "OLX", "titulo": "A", "preco": "R$ 450.000", "area": "80", "quartos": "2", "bairro": "Boa Viagem", "url": "https://x/1"}], p)
    aplicar_correcoes(r, '{"1": {"valor": 480000, "area": 100, "q": 3}}')
    assert (r[0].valor_oferta, r[0].area_m2, r[0].quartos, r[0].valor_m2) == (480000.0, 100.0, 3, 4800.0)
    aplicar_correcoes(r, "lixo")


def test_chave_do_usuario_vira_canal_de_coleta(monkeypatch):
    from app.main import chave_valida
    from app.scrapers.olx import OLXScraper
    monkeypatch.delenv("OLX_FETCH_TEMPLATE", raising=False)
    assert chave_valida("abc") is None and chave_valida("x y z " * 5) is None and chave_valida("a" * 10 + "<script>") is None
    k = "0123456789abcdef0123456789abcdef"
    assert chave_valida(f"  {k}\n") == k
    assert OLXScraper()._modelo_api() is None
    m = OLXScraper(k)._modelo_api()
    assert m.startswith("https://api.scrapingant.com/v2/general?url={url}") and k in m


def test_validar_chave_respostas(monkeypatch):
    import asyncio
    import httpx
    from app import main
    k = "0123456789abcdef0123456789abcdef"

    class Resp:
        def __init__(self, c, j=None): self.status_code, self._j = c, j or {}
        def json(self): return self._j

    def falso(codigo, j=None):
        class Cli:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **kw): return Resp(codigo, j)
        return Cli

    monkeypatch.setattr(httpx, "AsyncClient", falso(200, {"remained_credits": 9000, "plan_total_credits": 10000}))
    assert asyncio.run(main.validar_chave(k)) == {"ok": True, "restantes": 9000, "total": 10000}
    monkeypatch.setattr(httpx, "AsyncClient", falso(403))
    assert asyncio.run(main.validar_chave(k))["ok"] is False
    monkeypatch.setattr(httpx, "AsyncClient", falso(500))
    assert asyncio.run(main.validar_chave(k)).get("incerto") is True
    assert asyncio.run(main.validar_chave("lixo"))["ok"] is False
