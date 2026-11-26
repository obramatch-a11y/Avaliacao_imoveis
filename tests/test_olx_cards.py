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
