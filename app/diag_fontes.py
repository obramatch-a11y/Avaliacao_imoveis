"""Diagnóstico de fontes (somente leitura): mede, a partir do servidor, o que cada fonte devolve.

Regras deste módulo:
- uma requisição educada por recurso, sem retentativas, sem proxy, sem disfarce de navegador;
- User-Agent honesto, que identifica o aplicativo;
- respeita o robots.txt (regra do caminho mais específico, com curingas);
- não grava nada e não altera o comportamento da coleta existente;
- separa as causas: falha de conexão, bloqueio de acesso, erro de extração, sem anúncios.
"""
import asyncio
import gzip
import json
import os
import re
import sys
import time
from urllib.parse import quote, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.diagnostico import SINAIS_BLOQUEIO
from app.models import BuscaImovelInput
from app.scrapers.olx import OLXScraper

AGENTE = "InferenciaEstatistica-Diagnostico/1.0 (+https://avaliacao-imoveis-j39l.onrender.com; leitura unica, sem retentativas)"
CABECALHOS = {"User-Agent": AGENTE, "Accept-Language": "pt-BR,pt;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/markdown,*/*;q=0.5"}
TEMPO_LIMITE = 12.0
PRAZO_TOTAL = 85.0
LIMITE_SITEMAP_INDICE = 2_000_000
LIMITE_SITEMAP_FILHO = 6_000_000

# ---- classificação das causas ------------------------------------------------------------------

OK = "OK"
FALHA_CONEXAO = "FALHA_DE_CONEXAO"
BLOQUEIO = "BLOQUEIO_DE_ACESSO"
ERRO_EXTRACAO = "ERRO_DE_EXTRACAO"
SEM_ANUNCIOS = "SEM_ANUNCIOS"
ERRO_HTTP = "ERRO_HTTP"
ROBOTS_PROIBE = "ROBOTS_NAO_PERMITE"
NAO_EXECUTADO = "NAO_EXECUTADO"


def classificar(status: int | None, erro: str | None, sinais: list[str], n_lidos: int,
                total_declarado: int | None = None, conteudo_ok: bool = True) -> str:
    """Uma única causa por recurso, na ordem em que ela pode ser provada."""
    if erro:
        return FALHA_CONEXAO
    if status in (401, 403, 429):
        return BLOQUEIO
    if status is not None and status >= 500:
        return BLOQUEIO if sinais else ERRO_HTTP
    if status != 200:
        return ERRO_HTTP
    if n_lidos > 0:
        return OK
    if sinais and not conteudo_ok:
        return BLOQUEIO
    if total_declarado == 0:
        return SEM_ANUNCIOS
    return ERRO_EXTRACAO


# ---- medição de recursos -----------------------------------------------------------------------

def _rss_mb() -> float:
    try:
        paginas = int(open("/proc/self/statm").read().split()[1])
        return round(paginas * os.sysconf("SC_PAGE_SIZE") / 1e6, 1)
    except Exception:  # noqa: BLE001
        return -1.0


def _cgroup_mb() -> dict:
    """Memória do contêiner (é o que o Render limita), quando o sistema expõe."""
    for atual, limite in (("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
                          ("/sys/fs/cgroup/memory/memory.usage_in_bytes", "/sys/fs/cgroup/memory/memory.limit_in_bytes")):
        try:
            usado = int(open(atual).read().strip())
            lim_txt = open(limite).read().strip()
            lim = int(lim_txt) if lim_txt.isdigit() and int(lim_txt) < 1 << 50 else None
            return {"usado_mb": round(usado / 1e6, 1), "limite_mb": round(lim / 1e6, 1) if lim else None}
        except Exception:  # noqa: BLE001
            continue
    return {}


def _pico_mb() -> float:
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:  # noqa: BLE001
        return -1.0


class Medidor:
    """Mede tempo, CPU do processo e memória antes/depois de um recurso."""

    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.c0 = time.process_time()
        self.r0 = _rss_mb()

    def fechar(self) -> dict:
        return {
            "tempo_ms": int((time.perf_counter() - self.t0) * 1000),
            "cpu_ms": int((time.process_time() - self.c0) * 1000),
            "memoria_antes_mb": self.r0,
            "memoria_depois_mb": _rss_mb(),
        }


# ---- robots.txt (regra do caminho mais específico, com * e $) ----------------------------------

def _padrao_regex(padrao: str) -> re.Pattern:
    fim = padrao.endswith("$")
    corpo = re.escape(padrao[:-1] if fim else padrao).replace(r"\*", ".*")
    return re.compile("^" + corpo + ("$" if fim else ""))


def interpretar_robots(texto: str, agente: str = AGENTE) -> dict:
    """Devolve as regras do grupo mais específico para o agente (ou '*') e os sitemaps declarados."""
    token = agente.split("/")[0].lower()
    grupos: list[tuple[list[str], list[tuple[str, str]]]] = []
    atuais: list[str] = []
    regras: list[tuple[str, str]] = []
    lendo_agentes = False
    sitemaps: list[str] = []
    for bruta in texto.splitlines():
        linha = bruta.split("#", 1)[0].strip()
        if ":" not in linha:
            continue
        campo, valor = (p.strip() for p in linha.split(":", 1))
        campo = campo.lower()
        if campo == "user-agent":
            if not lendo_agentes:
                if atuais:
                    grupos.append((atuais, regras))
                atuais, regras = [], []
            atuais.append(valor.lower())
            lendo_agentes = True
        elif campo in ("allow", "disallow"):
            lendo_agentes = False
            regras.append((campo, valor))
        elif campo == "sitemap":
            sitemaps.append(valor)
    if atuais:
        grupos.append((atuais, regras))
    escolhido: list[tuple[str, str]] = []
    achou_proprio = False
    for agentes, regs in grupos:
        if any(a != "*" and a in token for a in agentes):
            escolhido, achou_proprio = regs, True
        elif "*" in agentes and not achou_proprio:
            escolhido = escolhido + regs
    return {"regras": escolhido, "sitemaps": sitemaps}


def robots_permite(regras: list[tuple[str, str]], caminho_e_consulta: str) -> bool:
    melhor_tam, permitido = -1, True
    for tipo, padrao in regras:
        if not padrao:
            continue
        if _padrao_regex(padrao).match(caminho_e_consulta):
            tam = len(padrao)
            if tam > melhor_tam or (tam == melhor_tam and tipo == "allow"):
                melhor_tam, permitido = tam, tipo == "allow"
    return permitido


async def _get(client: httpx.AsyncClient, url: str, limite_bytes: int | None = None):
    """Uma requisição; devolve (resposta|None, erro|None, bytes_lidos)."""
    try:
        resp = await client.get(url)
        corpo = resp.content
        if limite_bytes and len(corpo) > limite_bytes:
            return resp, None, len(corpo)
        return resp, None, len(corpo)
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {str(exc)[:120]}", 0


async def checar_robots(client: httpx.AsyncClient, url: str, cache: dict) -> dict:
    """Lê o robots.txt do host (uma vez) e diz se o endereço é permitido ao nosso agente.
    Regra do RFC 9309: 200 -> segue as regras; 4xx -> sem restrições; 5xx ou rede -> não acessar."""
    partes = urlsplit(url)
    host = f"{partes.scheme}://{partes.netloc}"
    if host not in cache:
        resp, erro, _ = await _get(client, host + "/robots.txt")
        if erro:
            cache[host] = {"estado": "inacessivel", "motivo": erro, "regras": [], "sitemaps": []}
        elif resp.status_code == 200:
            cache[host] = {"estado": "lido", "status": 200, **interpretar_robots(resp.text)}
        elif 400 <= resp.status_code < 500:
            cache[host] = {"estado": "indisponivel_4xx", "status": resp.status_code, "regras": [], "sitemaps": []}
        else:
            cache[host] = {"estado": "inacessivel", "status": resp.status_code, "regras": [], "sitemaps": []}
    info = cache[host]
    alvo = partes.path or "/"
    if partes.query:
        alvo += "?" + partes.query
    permitido = info["estado"] != "inacessivel" and robots_permite(info["regras"], alvo)
    return {"permitido": permitido, "estado_robots": info["estado"], "status_robots": info.get("status"), "sitemaps": info["sitemaps"]}


def _pular(motivo: str, robots: dict | None = None) -> dict:
    """Não acessou o recurso. Se o robots.txt nem pôde ser lido, a causa é de conexão/HTTP, não uma proibição."""
    rb = robots or {}
    if rb.get("estado_robots") == "inacessivel":
        classe = ERRO_HTTP if rb.get("status_robots") else FALHA_CONEXAO
        return {"classificacao": classe, "motivo": "robots.txt não pôde ser lido; por precaução (RFC 9309) o recurso não foi acessado", "robots": rb}
    return {"classificacao": ROBOTS_PROIBE, "motivo": motivo, "robots": rb}


# ---- Chaves na Mão: servidor MCP oficial -------------------------------------------------------

async def sonda_chaves_mcp(client: httpx.AsyncClient, params: BuscaImovelInput, robots_cache: dict) -> dict:
    from app.scrapers.chaves_mcp import MCP_URL, ClienteMCP, MCPErro, filtros_do_pedido, itens_do_resultado
    from app.validacao import cobertura_percentual

    rb = await checar_robots(client, MCP_URL, robots_cache)
    if not rb["permitido"]:
        return _pular("robots.txt não permite este endereço ao nosso agente", rb)
    m = Medidor()
    out: dict = {"url": MCP_URL, "robots": {k: rb[k] for k in ("permitido", "estado_robots")}}
    mcp = ClienteMCP(client)
    try:
        try:
            srv = await mcp.iniciar()
            out["initialize"] = {"servidor": srv.get("serverInfo"), "protocolo": srv.get("protocolVersion"),
                                 "capacidades": list((srv.get("capabilities") or {}).keys()), "sessao": bool(mcp.sessao)}
        except MCPErro as e:
            out["initialize"] = {"erro": str(e), "categoria": e.categoria}
            if e.categoria in ("conexao", "bloqueio"):
                raise
        ferramentas = await mcp.listar_ferramentas()
        out["ferramentas"] = [f.get("name") for f in ferramentas]
        busca = next((f for f in ferramentas if f.get("name") == "search_realty_listings"), None)
        out["esquema_search_realty_listings"] = json.dumps((busca or {}).get("inputSchema"), ensure_ascii=False)[:2500] if busca else None
        r = await mcp.chamar("search_realty_listings", {"filters": filtros_do_pedido(params), "page": 1, "pageSize": 20})
        itens, total, formato = itens_do_resultado(r)
        textos = [c.get("text", "") for c in (r.get("content") or []) if isinstance(c, dict)]
        out.update({
            "chaves_do_resultado": sorted(r.keys()), "formato_lido": formato, "total_declarado": total,
            "anuncios_lidos": len(itens), "cobertura_campos_pct": cobertura_percentual(itens),
            "primeiro_anuncio": itens[0] if itens else None, "amostra_bruta": ("\n".join(textos))[:700],
        })
        out["classificacao"] = classificar(200, None, [], len(itens), total)
    except MCPErro as e:
        out["erro"] = str(e)
        out["classificacao"] = {"conexao": FALHA_CONEXAO, "bloqueio": BLOQUEIO, "http": ERRO_HTTP}.get(e.categoria, ERRO_EXTRACAO)
    out.update(m.fechar())
    return out


# ---- Chaves na Mão: endpoint oficial para agentes ---------------------------------------------

def ler_markdown_chaves(texto: str) -> dict:
    """Lê a resposta em Markdown de /.well-known/search. Tolerante: campos ausentes ficam vazios."""
    total = None
    m = re.search(r"([\d.]+)\s+an[uú]ncios?\s+encontrados?", texto, re.I)
    if m:
        total = int(m.group(1).replace(".", ""))
    blocos = re.split(r"\n\s*(?:-{3,}|\*{3,}|_{3,})\s*\n", texto)
    itens = []
    for b in blocos:
        url = re.search(r"https?://[^\s)\]>\"']+/imovel/[^\s)\]>\"']+", b)
        if not url or "R$" not in b:
            continue

        def campo(nome: str) -> str:
            r = re.search(rf"{nome}\**\s*:\s*\**\s*(.+)", b, re.I)
            return re.sub(r"[*_`]", "", r.group(1)).strip() if r else ""

        carac = campo("Caracter[ií]sticas") or b
        area = re.search(r"(\d+(?:[.,]\d+)?)\s*m(?:²|2)", carac) or re.search(r"(\d+(?:[.,]\d+)?)\s*m(?:²|2)", b)
        quartos = re.search(r"(\d+)\s*quartos?", carac, re.I)
        local = campo("Local")
        titulo = re.search(r"^\s*#+\s*(.+)$", b, re.M)
        itens.append({
            "titulo": titulo.group(1).strip() if titulo else "",
            "url": url.group(0).rstrip(".,;"),
            "preco": campo("Pre[cç]o"),
            "local": local,
            "bairro": local.split(",")[0].strip() if local else "",
            "area_m2": area.group(1) if area else "",
            "quartos": quartos.group(1) if quartos else "",
            "tipo": campo("Tipo"),
        })
    return {"total_declarado": total, "itens": itens}


async def sonda_chaves_busca(client: httpx.AsyncClient, params: BuscaImovelInput, robots_cache: dict) -> dict:
    tipo = {"APARTAMENTO": "apartamento", "CASA": "casa", "TERRENO": "terreno", "COMERCIAL": "imóvel comercial"}.get(params.tipo_imovel, "apartamento")
    acao = "para alugar" if params.finalidade == "LOCACAO" else "para comprar"
    q = f"{tipo} {acao} em {params.cidade} {params.uf.upper()}"
    url = "https://www.chavesnamao.com.br/.well-known/search?q=" + quote(q)
    rb = await checar_robots(client, url, robots_cache)
    if not rb["permitido"]:
        return _pular("robots.txt não permite este endereço ao nosso agente", rb)
    m = Medidor()
    resp, erro, nbytes = await _get(client, url)
    out: dict = {"url": url, "robots": {k: rb[k] for k in ("permitido", "estado_robots")}}
    if resp is None:
        out.update(m.fechar())
        out.update({"erro": erro, "classificacao": classificar(None, erro, [], 0)})
        return out
    texto = resp.text
    lido = ler_markdown_chaves(texto) if resp.status_code == 200 else {"total_declarado": None, "itens": []}
    itens = lido["itens"]
    sinais = [k for k, rx in SINAIS_BLOQUEIO.items() if rx.search(texto[:100_000])]
    campos = ("url", "preco", "area_m2", "quartos", "bairro")
    out.update(m.fechar())
    out.update({
        "status": resp.status_code, "bytes": nbytes, "content_type": resp.headers.get("content-type", ""),
        "total_declarado": lido["total_declarado"], "anuncios_lidos": len(itens),
        "cobertura_campos": {c: sum(1 for i in itens if i.get(c)) for c in campos} if itens else {},
        "tem_foto_no_retorno": bool(re.search(r"\.(?:jpe?g|webp|png)\b", texto, re.I)),
        "amostra_formato": texto[:500],
        "primeiro_anuncio": itens[0] if itens else None,
        "sinais_bloqueio": sinais,
        "classificacao": classificar(resp.status_code, None, sinais, len(itens), lido["total_declarado"]),
    })
    out["_urls"] = [i["url"] for i in itens]
    return out


# ---- Chaves na Mão: sitemaps e dados estruturados ---------------------------------------------

def _locs(xml: str) -> list[str]:
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)


def _mesmo_dominio(url: str, dominio: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == dominio or host.endswith("." + dominio)


async def _baixar_xml(client: httpx.AsyncClient, url: str, limite: int):
    resp, erro, nbytes = await _get(client, url)
    if resp is None:
        return None, erro, 0, None
    if nbytes > limite:
        return resp, None, nbytes, "grande_demais"
    corpo = resp.content
    if url.endswith(".gz") or corpo[:2] == b"\x1f\x8b":
        try:
            corpo = gzip.decompress(corpo)
        except Exception:  # noqa: BLE001
            return resp, None, nbytes, "gzip_invalido"
    return resp, None, nbytes, corpo.decode("utf-8", "replace")


async def sonda_chaves_sitemap(client: httpx.AsyncClient, robots_cache: dict) -> dict:
    url = "https://www.chavesnamao.com.br/sitemap-2026-realty-ads-index.xml"
    rb = await checar_robots(client, url, robots_cache)
    if not rb["permitido"]:
        return _pular("robots.txt não permite este endereço ao nosso agente", rb)
    m = Medidor()
    resp, erro, nbytes, xml = await _baixar_xml(client, url, LIMITE_SITEMAP_INDICE)
    out: dict = {"url_indice": url, "sitemaps_declarados_no_robots": rb["sitemaps"]}
    if resp is None:
        out.update(m.fechar())
        out.update({"erro": erro, "classificacao": classificar(None, erro, [], 0)})
        return out
    locs = _locs(xml) if isinstance(xml, str) and xml not in ("grande_demais", "gzip_invalido") else []
    out.update({"status": resp.status_code, "bytes_indice": nbytes, "entradas_no_indice": len(locs), "amostra_indice": locs[:3]})
    filhos = [u for u in locs if _mesmo_dominio(u, "chavesnamao.com.br")]
    if filhos:
        filho = filhos[0]
        rf = await checar_robots(client, filho, robots_cache)
        if rf["permitido"]:
            resp2, erro2, n2, xml2 = await _baixar_xml(client, filho, LIMITE_SITEMAP_FILHO)
            if resp2 is not None and isinstance(xml2, str) and xml2 not in ("grande_demais", "gzip_invalido"):
                urls = _locs(xml2)
                out["primeiro_sitemap_filho"] = {
                    "url": filho, "status": resp2.status_code, "bytes": n2, "urls_de_anuncio": len(urls),
                    "amostra": urls[:3], "com_imovel_no_caminho": sum(1 for u in urls if "/imovel/" in u),
                }
            else:
                out["primeiro_sitemap_filho"] = {"url": filho, "erro": erro2 or xml2 or "sem_corpo", "bytes": n2}
        else:
            out["primeiro_sitemap_filho"] = {"url": filho, "classificacao": ROBOTS_PROIBE}
    out.update(m.fechar())
    ok = bool(locs) and resp.status_code == 200
    out["classificacao"] = classificar(resp.status_code, None, [], 1 if ok else 0)
    return out


def ler_estruturados(html: str) -> dict:
    soup = BeautifulSoup(html[:3_000_000], "lxml")
    blocos, tipos = [], []
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            dado = json.loads(s.string or s.get_text() or "")
        except Exception:  # noqa: BLE001
            continue
        pilha = dado if isinstance(dado, list) else [dado]
        while pilha:
            d = pilha.pop()
            if isinstance(d, dict):
                if "@graph" in d and isinstance(d["@graph"], list):
                    pilha.extend(d["@graph"])
                t = d.get("@type")
                if t:
                    tipos.extend(t if isinstance(t, list) else [t])
                blocos.append(d)
    campos = set()
    n_imagens = 0
    for d in blocos:
        for k in ("name", "description", "offers", "price", "floorSize", "numberOfRooms", "numberOfBedrooms",
                  "numberOfBathroomsTotal", "address", "geo", "image", "url"):
            if k in d:
                campos.add(k)
        img = d.get("image")
        n_imagens = max(n_imagens, len(img) if isinstance(img, list) else (1 if img else 0))
    og = [m.get("content") for m in soup.find_all("meta", attrs={"property": "og:image"}) if m.get("content")]
    return {
        "json_ld_blocos": len(blocos), "tipos_schema_org": sorted(set(map(str, tipos)))[:12],
        "campos_no_json_ld": sorted(campos), "imagens_no_json_ld": n_imagens, "og_image": len(og),
        "next_data": soup.find("script", id="__NEXT_DATA__") is not None,
        "titulo": (soup.title.string.strip() if soup.title and soup.title.string else "")[:120],
    }


async def sonda_chaves_anuncio(client: httpx.AsyncClient, url_anuncio: str | None, robots_cache: dict) -> dict:
    if not url_anuncio or not _mesmo_dominio(url_anuncio, "chavesnamao.com.br"):
        return {"classificacao": NAO_EXECUTADO, "motivo": "a busca oficial não devolveu um endereço de anúncio do domínio"}
    rb = await checar_robots(client, url_anuncio, robots_cache)
    if not rb["permitido"]:
        return _pular("robots.txt não permite este endereço ao nosso agente", rb)
    m = Medidor()
    resp, erro, nbytes = await _get(client, url_anuncio)
    out: dict = {"url": url_anuncio}
    if resp is None:
        out.update(m.fechar())
        out.update({"erro": erro, "classificacao": classificar(None, erro, [], 0)})
        return out
    texto = resp.text if resp.status_code == 200 else ""
    est = ler_estruturados(texto) if texto else {}
    sinais = [k for k, rx in SINAIS_BLOQUEIO.items() if rx.search(texto[:100_000])]
    out.update(m.fechar())
    out.update({"status": resp.status_code, "bytes": nbytes, **est, "sinais_bloqueio": sinais})
    out["classificacao"] = classificar(resp.status_code, None, sinais, 1 if est.get("json_ld_blocos") else 0,
                                       conteudo_ok=bool(texto))
    return out


# ---- OLX (somente o que o servidor consegue ler, sem disfarce) ---------------------------------

async def sonda_olx(client: httpx.AsyncClient, params: BuscaImovelInput, robots_cache: dict) -> dict:
    from app.diagnostico import _analisar

    s = OLXScraper(None)
    url = s._montar_url(params, 1, "caminho")
    rb = await checar_robots(client, url, robots_cache)
    if not rb["permitido"]:
        return _pular("robots.txt não permite este endereço ao nosso agente (ou não pôde ser lido)", rb)
    m = Medidor()
    resp, erro, _ = await _get(client, url)
    if resp is None:
        out = {"url": url, **m.fechar(), "erro": erro, "classificacao": classificar(None, erro, [], 0)}
        return out
    a = _analisar(s, resp, 0, None)
    texto = resp.text or ""
    a.update(m.fechar())
    a.update({"url": url, "robots": {k: rb[k] for k in ("permitido", "estado_robots", "status_robots")},
              "layout_next_f": "self.__next_f" in texto[:3_000_000]})
    sinais = a.get("sinais_bloqueio", [])
    total = 0 if re.search(r"nenhum an[uú]ncio|0 resultados", texto[:400_000], re.I) else None
    a["classificacao"] = classificar(resp.status_code, None, sinais, a.get("anuncios_lidos", 0), total,
                                     conteudo_ok=len(texto) > 20_000)
    return a


# ---- orquestração ------------------------------------------------------------------------------

async def diagnosticar_fontes(params: BuscaImovelInput, transporte: httpx.AsyncBaseTransport | None = None) -> dict:
    inicio = time.perf_counter()
    ambiente = {
        "python": sys.version.split()[0],
        "memoria_processo_inicio_mb": _rss_mb(), "memoria_conteiner": _cgroup_mb(),
        "agente_usado": AGENTE,
        "sem_proxy": True, "sem_disfarce_de_navegador": True,
    }
    robots_cache: dict = {}
    resultado: dict = {"ambiente": ambiente, "fontes": {}}
    async with httpx.AsyncClient(headers=CABECALHOS, timeout=TEMPO_LIMITE, follow_redirects=True, transport=transporte) as client:
        async def rodar(nome, coro):
            if time.perf_counter() - inicio > PRAZO_TOTAL:
                resultado["fontes"][nome] = {"classificacao": NAO_EXECUTADO, "motivo": "prazo total do diagnóstico esgotado"}
                return None
            try:
                r = await asyncio.wait_for(coro, timeout=TEMPO_LIMITE * 4)
            except Exception as exc:  # noqa: BLE001
                r = {"classificacao": FALHA_CONEXAO, "erro": f"{type(exc).__name__}: {str(exc)[:120]}"}
            resultado["fontes"][nome] = r
            return r

        await rodar("chaves_mcp", sonda_chaves_mcp(client, params, robots_cache))
        busca = await rodar("chaves_busca_oficial", sonda_chaves_busca(client, params, robots_cache))
        urls = (busca or {}).pop("_urls", []) if busca else []
        await rodar("chaves_sitemap", sonda_chaves_sitemap(client, robots_cache))
        await rodar("chaves_pagina_anuncio", sonda_chaves_anuncio(client, urls[0] if urls else None, robots_cache))
        await rodar("olx_listagem", sonda_olx(client, params, robots_cache))
    ambiente.update({
        "memoria_processo_fim_mb": _rss_mb(), "pico_memoria_processo_mb": _pico_mb(),
        "cpu_total_ms": int(time.process_time() * 1000), "duracao_total_ms": int((time.perf_counter() - inicio) * 1000),
        "memoria_conteiner_fim": _cgroup_mb(),
    })
    resultado["resumo"] = {n: f.get("classificacao") for n, f in resultado["fontes"].items()}
    return resultado
