"""Diagnóstico medido da coleta no OLX: uma única requisição educada por canal, sem retentativas
e sem disfarce. Serve para saber, com números, o que o OLX devolve para este servidor."""
import re
import time
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from app.models import BuscaImovelInput
from app.scrapers.olx import OLXScraper

SINAIS_BLOQUEIO = {
    "cloudflare": re.compile(r"cloudflare|cf-chl|challenge-platform|just a moment", re.I),
    "captcha": re.compile(r"captcha|hcaptcha|recaptcha|turnstile", re.I),
    "acesso_negado": re.compile(r"access denied|acesso negado|forbidden|unusual traffic|tráfego incomum", re.I),
}


def _classificar(status: int | None, tem_next: bool, n_itens: int, sinais: list[str], erro: str | None) -> str:
    if erro:
        return "ERRO_DE_REDE"
    if status == 200 and n_itens > 0:
        return "OK_COM_ANUNCIOS"
    if status == 200 and tem_next:
        return "200_SEM_ANUNCIOS_NA_BUSCA"
    if status == 200 and sinais:
        return "200_COM_DESAFIO_ANTIBOT"
    if status == 200:
        return "200_INCOMPLETO"
    if status == 403:
        return "BLOQUEADO_403"
    if status == 429:
        return "LIMITE_DE_TAXA_429"
    if status in (423, 503):
        return "DESAFIO_ANTIBOT_%s" % status
    return "HTTP_%s" % status


def _analisar(scraper: OLXScraper, resp: httpx.Response | None, ms: int, erro: str | None) -> dict:
    out: dict = {"tempo_ms": ms, "erro": erro}
    if resp is None:
        out["classificacao"] = _classificar(None, False, 0, [], erro)
        return out
    texto = resp.text or ""
    soup = BeautifulSoup(texto[:3_000_000], "lxml")
    tem_next = soup.find("script", id="__NEXT_DATA__") is not None
    n_ld = len(soup.find_all("script", attrs={"type": "application/ld+json"}))
    itens = scraper._extrair_de_next_data(soup) if tem_next else []
    via = "next_data"
    if not itens:
        itens = scraper._extrair_de_html_cards(soup)
        via = "html_cards"
    sinais = [k for k, rx in SINAIS_BLOQUEIO.items() if rx.search(texto[:200_000])]
    h = {k.lower(): v for k, v in resp.headers.items()}
    campos = ("preco", "area", "quartos", "banheiros", "vagas", "bairro", "fotos", "url")
    cobertura = {c: sum(1 for i in itens if i.get(c)) for c in campos} if itens else {}
    out.update({
        "status": resp.status_code,
        "bytes": len(resp.content),
        "content_type": h.get("content-type", ""),
        "servidor": h.get("server", ""),
        "cf_ray": bool(h.get("cf-ray")),
        "next_data": tem_next,
        "json_ld_blocos": n_ld,
        "anuncios_lidos": len(itens),
        "lido_via": via if itens else "",
        "cobertura_campos": cobertura,
        "sinais_bloqueio": sinais,
        "classificacao": _classificar(resp.status_code, tem_next, len(itens), sinais, None),
    })
    return out


async def _uma_requisicao(scraper: OLXScraper, alvo: str, timeout: float, proxy: str | None = None):
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(headers=scraper.HEADERS, timeout=timeout, follow_redirects=True, proxy=proxy) as c:
            resp = await c.get(alvo)
        return _analisar(scraper, resp, int((time.perf_counter() - t0) * 1000), None)
    except Exception as exc:  # noqa: BLE001
        return _analisar(scraper, None, int((time.perf_counter() - t0) * 1000), f"{type(exc).__name__}: {str(exc)[:120]}")


async def ip_de_saida() -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            return (await c.get("https://api.ipify.org")).text.strip()[:45]
    except Exception:  # noqa: BLE001
        return "indisponível"


async def diagnosticar(params: BuscaImovelInput, chave_api: str | None = None) -> dict:
    """Mede o que o OLX devolve. Canal 'direto' (IP deste servidor) e, se houver, canal 'api'."""
    s = OLXScraper(chave_api)
    url = s._montar_url(params, 1, "caminho")
    resultado: dict = {"url_consultada": url, "ip_de_saida_do_servidor": await ip_de_saida(), "canais": {}}
    resultado["canais"]["direto"] = await _uma_requisicao(s, url, 20.0)
    modelo = s._modelo_api()
    if modelo:
        alvo = modelo.replace("{url}", quote(url, safe=""))
        resultado["canais"]["api_terceiro"] = await _uma_requisicao(s, alvo, 90.0)
    else:
        resultado["canais"]["api_terceiro"] = {"classificacao": "NAO_CONFIGURADO"}
    d = resultado["canais"]["direto"]["classificacao"]
    a = resultado["canais"]["api_terceiro"]["classificacao"]
    if d == "OK_COM_ANUNCIOS":
        leitura = "O servidor lê o OLX direto: a dependência de API de terceiro pode ser removida."
    elif a == "OK_COM_ANUNCIOS":
        leitura = "Direto falha e a API de terceiro funciona: o bloqueio é por origem (IP do servidor), não por leitura dos dados."
    elif a == "NAO_CONFIGURADO":
        leitura = "Direto falhou e não há canal alternativo para comparar: entre com o Google (chave guardada na conta) para comparar com o canal de terceiro."
    else:
        leitura = "Nenhum canal trouxe anúncios: olhar status e sinais de cada canal."
    resultado["leitura"] = leitura
    return resultado
