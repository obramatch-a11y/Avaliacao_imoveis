"""Extração e validação de fotografias de anúncios (sem contornar bloqueios)."""
import json
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Tag

# Só aceitamos links https de domínios do próprio OLX (evita SSRF e conteúdo de terceiros).
DOMINIOS_OK = ("olx.com.br", "olxcdn.com")
EXT_RUINS = (".svg", ".gif", ".ico")
PALAVRAS_RUINS = ("logo", "icon", "placeholder", "avatar", "sprite", "banner")
MAX_FOTOS = 30


def host_permitido(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    host = (p.hostname or "").lower()
    return p.scheme == "https" and any(host == d or host.endswith("." + d) for d in DOMINIOS_OK)


def _foto_valida(url: str) -> bool:
    if not url or not host_permitido(url):
        return False
    baixo = url.lower().split("?")[0]
    return not baixo.endswith(EXT_RUINS) and not any(p in baixo for p in PALAVRAS_RUINS)


def _maior_do_srcset(srcset: str) -> str:
    melhor, peso = "", -1.0
    for parte in srcset.split(","):
        pedacos = parte.strip().split()
        if not pedacos:
            continue
        w = 1.0
        if len(pedacos) > 1:
            m = re.match(r"([\d.]+)[wx]", pedacos[1])
            w = float(m.group(1)) if m else 1.0
        if w > peso:
            melhor, peso = pedacos[0], w
    return melhor


def _unicas(urls: list[str]) -> list[str]:
    vistos, out = set(), []
    for u in urls:
        if _foto_valida(u) and u not in vistos:
            vistos.add(u)
            out.append(u)
    return out[:MAX_FOTOS]


def fotos_de_tag(tag: Tag) -> list[str]:
    """Fotos visíveis em um cartão de listagem (inclui carregamento diferido)."""
    urls: list[str] = []
    for img in tag.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src"):
            if img.get(attr):
                urls.append(str(img[attr]))
        if img.get("srcset"):
            urls.append(_maior_do_srcset(str(img["srcset"])))
    for src in tag.find_all("source"):
        if src.get("srcset"):
            urls.append(_maior_do_srcset(str(src["srcset"])))
    return _unicas(urls)


def fotos_de_anuncio(html: str) -> list[str]:
    """Fotos da página do anúncio: dados estruturados, JSON da página, Open Graph e galeria."""
    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []

    for s in soup.find_all("script", type="application/ld+json"):
        try:
            dados = json.loads(s.string or "")
        except ValueError:
            continue
        for d in (dados if isinstance(dados, list) else [dados]):
            img = d.get("image") if isinstance(d, dict) else None
            if isinstance(img, str):
                urls.append(img)
            elif isinstance(img, list):
                urls += [i if isinstance(i, str) else str(i.get("url", "")) for i in img if i]

    nd = soup.find("script", id="__NEXT_DATA__")
    if nd and nd.string:
        try:
            dados = json.loads(nd.string)
            ad = dados.get("props", {}).get("pageProps", {}).get("ad", {}) or {}
            for im in ad.get("images", []) or []:
                if isinstance(im, dict):
                    urls.append(str(im.get("original") or im.get("originalWebp") or im.get("url") or ""))
        except ValueError:
            pass

    for m in soup.find_all("meta", attrs={"property": "og:image"}):
        urls.append(str(m.get("content", "")))
    urls += fotos_de_tag(soup)
    return _unicas(urls)
