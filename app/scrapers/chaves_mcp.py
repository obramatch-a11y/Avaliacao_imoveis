"""Chaves na Mão pelo canal oficial para agentes: servidor MCP (JSON-RPC sobre HTTP), consumido direto
pelo backend Python (sem modelo de IA, sem chave, sem proxy, sem disfarce).

Fontes documentadas pelo próprio site:
- /.well-known/mcp/server-card.json  -> endpoint https://www.chavesnamao.com.br/api/mcp/ (streamable-http, sem autenticação)
- /.well-known/agent-skills/search-listings/SKILL.md -> filtros: transaction (venda|aluguel), propertyType
  (apartamento|casa|terreno|comercial|rural), city, state (2 letras), neighborhood, minPrice/maxPrice, minArea/maxArea,
  bedrooms, bathrooms, parkingSpots, amenities; paginação page 1-20 e pageSize 1-20 (fora de "filters").
- Não há ferramenta de detalhamento; coordenadas, condomínio e IPTU não são documentados; fotos só pela página do anúncio.

Ordem de uso: MCP -> /.well-known/search (até 15 resultados, texto livre) -> leitura das páginas públicas (raspador antigo).
"""
import asyncio
import json
import re
from typing import Any

import httpx

from app.models import BuscaImovelInput
from app.scrapers.chaves import ChavesNaMaoScraper
from app.scrapers.olx import OLXScraper

MCP_URL = "https://www.chavesnamao.com.br/api/mcp/"
BUSCA_URL = "https://www.chavesnamao.com.br/.well-known/search"
AGENTE = "InferenciaEstatistica/1.0 (+https://avaliacao-imoveis-j39l.onrender.com; consulta via MCP oficial, sem retentativas agressivas)"
CABECALHOS_MCP = {
    "User-Agent": AGENTE,
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
VERSAO_PROTOCOLO = "2025-03-26"
PAGINA_MAX = 20
TAMANHO_MAX = 15  # limite real do servidor (esquema: pageSize máximo 15); page máximo 20 -> até 300 anúncios por consulta
IMAGENS_BASE = "https://www.chavesnamao.com.br/imn/0640x0450/N/40/imoveis/"  # padrão observado na página pública do anúncio

TIPOS = {"APARTAMENTO": "apartamento", "CASA": "casa", "TERRENO": "terreno", "COMERCIAL": "comercial"}
TRANSACAO = {"VENDA": "venda", "LOCACAO": "aluguel"}


class MCPErro(Exception):
    """Falha ao falar com o servidor MCP (rede, HTTP ou JSON-RPC)."""

    def __init__(self, mensagem: str, categoria: str = "erro"):
        super().__init__(mensagem)
        self.categoria = categoria  # "conexao" | "bloqueio" | "http" | "protocolo" | "ferramenta"


# ---- cliente JSON-RPC ---------------------------------------------------------------------------

def _mensagem_do_corpo(resp: httpx.Response, id_esperado: int | None) -> dict | None:
    tipo = resp.headers.get("content-type", "")
    texto = resp.text or ""
    candidatos: list[Any] = []
    if "text/event-stream" in tipo or texto.lstrip().startswith(("event:", "data:")):
        for linha in texto.splitlines():
            if linha.startswith("data:"):
                try:
                    candidatos.append(json.loads(linha[5:].strip()))
                except ValueError:
                    continue
    else:
        try:
            dado = json.loads(texto)
        except ValueError:
            return None
        candidatos = dado if isinstance(dado, list) else [dado]
    for c in candidatos:
        if isinstance(c, dict) and (id_esperado is None or c.get("id") == id_esperado):
            return c
    return None


class ClienteMCP:
    def __init__(self, client: httpx.AsyncClient, url: str = MCP_URL):
        self.client, self.url = client, url
        self.sessao: str | None = None
        self.servidor: dict = {}
        self._id = 0
        self.iniciado = False

    async def _post(self, payload: dict, espera_resposta: bool = True) -> dict | None:
        cab = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if self.sessao:
            cab["Mcp-Session-Id"] = self.sessao
        if self.iniciado:
            cab["MCP-Protocol-Version"] = VERSAO_PROTOCOLO
        try:
            resp = await self.client.post(self.url, json=payload, headers=cab)
        except httpx.HTTPError as exc:
            raise MCPErro(f"{type(exc).__name__}: {str(exc)[:120]}", "conexao")
        if resp.status_code in (401, 403, 429):
            raise MCPErro(f"HTTP {resp.status_code}", "bloqueio")
        if resp.status_code >= 400:
            raise MCPErro(f"HTTP {resp.status_code}: {(resp.text or '')[:160]}", "http")
        if resp.headers.get("mcp-session-id"):
            self.sessao = resp.headers["mcp-session-id"]
        if not espera_resposta:
            return None
        msg = _mensagem_do_corpo(resp, payload.get("id"))
        if msg is None:
            raise MCPErro(f"resposta sem mensagem JSON-RPC ({resp.headers.get('content-type', '')}): {(resp.text or '')[:160]}", "protocolo")
        if "error" in msg:
            e = msg["error"] or {}
            raise MCPErro(f"JSON-RPC {e.get('code')}: {str(e.get('message'))[:200]} {json.dumps(e.get('data'), ensure_ascii=False)[:600] if e.get('data') else ''}".strip(), "ferramenta")
        return msg.get("result") if isinstance(msg.get("result"), dict) else {"valor": msg.get("result")}

    async def iniciar(self) -> dict:
        self._id += 1
        r = await self._post({
            "jsonrpc": "2.0", "id": self._id, "method": "initialize",
            "params": {"protocolVersion": VERSAO_PROTOCOLO, "capabilities": {},
                       "clientInfo": {"name": "inferencia-estatistica", "version": "1.0"}},
        })
        self.servidor = r or {}
        self.iniciado = True
        try:
            await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, espera_resposta=False)
        except MCPErro:
            pass  # servidores sem estado podem ignorar a notificação
        return self.servidor

    async def listar_ferramentas(self) -> list[dict]:
        self._id += 1
        r = await self._post({"jsonrpc": "2.0", "id": self._id, "method": "tools/list", "params": {}})
        return (r or {}).get("tools") or []

    async def chamar(self, nome: str, argumentos: dict) -> dict:
        self._id += 1
        r = await self._post({"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                              "params": {"name": nome, "arguments": argumentos}})
        if r and r.get("isError"):
            texto = " ".join(c.get("text", "") for c in (r.get("content") or []) if isinstance(c, dict))
            raise MCPErro(f"ferramenta devolveu erro: {texto[:200]}", "ferramenta")
        return r or {}


# ---- leitura tolerante do resultado -------------------------------------------------------------

def _chave(d: dict, *nomes: str):
    baixo = {str(k).lower(): v for k, v in d.items()}
    for n in nomes:
        if n.lower() in baixo and baixo[n.lower()] not in (None, "", [], {}):
            return baixo[n.lower()]
    return None


def _acha_lista(obj: Any, profundidade: int = 0) -> list[dict]:
    """Primeira lista de dicionários que parece ser de anúncios (tem url/link)."""
    if profundidade > 5:
        return []
    if isinstance(obj, list):
        itens = [i for i in obj if isinstance(i, dict)]
        if itens and any(_chave(i, "url", "link", "href") for i in itens):
            return itens
        for i in obj:
            r = _acha_lista(i, profundidade + 1)
            if r:
                return r
    elif isinstance(obj, dict):
        for v in obj.values():
            r = _acha_lista(v, profundidade + 1)
            if r:
                return r
    return []


def _numero(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"\d[\d.]*(?:,\d+)?", v)
        if m:
            try:
                return float(m.group(0).replace(".", "").replace(",", "."))
            except ValueError:
                return None
    return None


def _fotos(d: dict) -> list[str]:
    saida: list[str] = []
    for nome in ("images", "photos", "fotos", "pictures", "image", "photo", "thumbnail", "imageurl", "foto"):
        v = _chave(d, nome)
        if v is None:
            continue
        for el in (v if isinstance(v, list) else [v]):
            url = el.get("url") if isinstance(el, dict) else el
            if isinstance(url, str) and url and not url.startswith("http") and re.match(r"^\d+/\d+/.+\.(jpe?g|png|webp)$", url):
                url = IMAGENS_BASE + url  # o MCP devolve só o caminho relativo da foto
            if isinstance(url, str) and url.startswith("http") and url not in saida:
                saida.append(url)
    return saida[:30]


def registro_de_item(d: dict) -> dict:
    """Um anúncio do MCP -> o dicionário bruto que o normalizador do app entende."""
    loc = _chave(d, "location", "localizacao", "localização", "address", "endereco", "local")
    bairro = cidade = ""
    if isinstance(loc, dict):
        bairro = str(_chave(loc, "neighborhood", "bairro") or "")
        cidade = str(_chave(loc, "city", "cidade") or "")
        texto_loc = ", ".join(x for x in (bairro, cidade) if x)
    else:
        texto_loc = str(loc or "")
        bairro = texto_loc.split(",")[0].strip() if texto_loc else ""
    bairro = bairro or str(_chave(d, "neighborhood", "bairro") or "")
    area = _chave(d, "area", "areaM2", "area_m2", "usableArea", "area_util", "areaUtil", "size")
    preco = _numero(_chave(d, "priceBRL", "price", "preco", "preço", "valor", "amount"))
    titulo = str(_chave(d, "title", "titulo", "título", "name") or "")
    url = str(_chave(d, "url", "link", "href") or "")
    quartos = _chave(d, "bedrooms", "quartos", "dormitorios")
    banheiros = _chave(d, "bathrooms", "banheiros")
    vagas = _chave(d, "parkingSpots", "parking", "vagas", "garagens", "parkingSpaces")
    return {
        "fonte": "Chaves na Mão",
        "titulo": titulo,
        "preco": f"R$ {int(preco):,}".replace(",", ".") if preco else "",
        "bairro": bairro,
        "cidade_origem": cidade,
        "area": str(_numero(area)) if _numero(area) else "",
        "quartos": str(int(_numero(quartos))) if _numero(quartos) is not None else "",
        "banheiros": str(int(_numero(banheiros))) if _numero(banheiros) is not None else "",
        "vagas": str(int(_numero(vagas))) if _numero(vagas) is not None else "",
        "condominio": str(_chave(d, "condominio", "condoFee", "condominiumFee") or ""),
        "iptu": str(_chave(d, "iptu") or ""),
        "detalhes": f"{titulo} {texto_loc}".strip(),
        "descricao": str(_chave(d, "description", "descricao", "descrição", "body", "text", "about") or "")[:3000],
        "url": url,
        "fotos": _fotos(d),
    }


def itens_do_resultado(resultado: dict) -> tuple[list[dict], int | None, str]:
    """Resultado de tools/call -> (anúncios brutos, total declarado, formato lido)."""
    if isinstance(resultado.get("structuredContent"), (dict, list)):
        lista = _acha_lista(resultado["structuredContent"])
        if lista:
            total = _total(resultado["structuredContent"])
            return [registro_de_item(i) for i in lista], total, "structuredContent"
    textos = [c.get("text", "") for c in (resultado.get("content") or []) if isinstance(c, dict) and c.get("type") == "text"]
    texto = "\n".join(textos)
    try:
        dado = json.loads(texto)
    except ValueError:
        dado = None
    if dado is not None:
        lista = _acha_lista(dado)
        if lista:
            return [registro_de_item(i) for i in lista], _total(dado), "json_em_texto"
    from app.diag_fontes import ler_markdown_chaves
    md = ler_markdown_chaves(texto)
    if md["itens"]:
        itens = []
        for i in md["itens"]:
            itens.append({"fonte": "Chaves na Mão", "titulo": i["titulo"], "preco": i["preco"], "bairro": i["bairro"],
                          "cidade_origem": "", "area": i["area_m2"], "quartos": i["quartos"], "banheiros": "", "vagas": "",
                          "condominio": "", "iptu": "", "detalhes": f"{i['titulo']} {i['local']}", "descricao": "",
                          "url": i["url"], "fotos": []})
        return itens, md["total_declarado"], "markdown"
    return [], _total(dado) if dado is not None else md["total_declarado"], "nao_reconhecido"


def _total(obj: Any) -> int | None:
    if isinstance(obj, dict):
        for k in ("total", "totalCount", "totalResults", "count", "totalItems", "total_declarado"):
            v = _chave(obj, k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return int(v)
        for v in obj.values():
            if isinstance(v, dict):
                r = _total(v)
                if r is not None:
                    return r
    return None


def filtros_do_pedido(params: BuscaImovelInput) -> dict:
    f: dict = {"transaction": TRANSACAO[params.finalidade], "propertyType": TIPOS.get(params.tipo_imovel, "apartamento"),
               "city": params.cidade.strip(), "state": params.uf.upper()}
    if params.bairro:
        f["neighborhood"] = params.bairro.strip()
    if params.preco_min:
        f["minPrice"] = int(params.preco_min)
    if params.preco_max:
        f["maxPrice"] = int(params.preco_max)
    if params.area_min:
        f["minArea"] = float(params.area_min)
    if params.area_max:
        f["maxArea"] = float(params.area_max)
    return f


def argumentos_busca(params: BuscaImovelInput, pagina: int, com_paginacao: bool = True) -> dict:
    """O esquema real do servidor exige `query` (texto livre, 1-200 caracteres); os filtros estruturados prevalecem sobre ela."""
    tipo = TIPOS.get(params.tipo_imovel, "apartamento")
    local = " ".join(x for x in (params.bairro.strip(), params.cidade.strip(), params.uf.upper()) if x)
    a: dict = {"query": f"{tipo} {local}"[:200], "filters": filtros_do_pedido(params)}
    if com_paginacao:
        a.update({"page": pagina, "pageSize": TAMANHO_MAX})
    return a


async def chamar_busca(mcp: "ClienteMCP", params: BuscaImovelInput, pagina: int) -> dict:
    try:
        return await mcp.chamar("search_realty_listings", argumentos_busca(params, pagina))
    except MCPErro as e:
        if e.categoria == "ferramenta" and "-32602" in str(e):
            return await mcp.chamar("search_realty_listings", argumentos_busca(params, pagina, com_paginacao=False))
        raise


# ---- raspador no formato do app -----------------------------------------------------------------

class ChavesNaMaoMCPScraper(OLXScraper):
    nome_fonte = "Chaves na Mão"

    def __init__(self, chave_api: str | None = None):
        super().__init__(chave_api)
        self.canal_usado = ""
        self.total_declarado: int | None = None
        self.fonte_respondeu = False  # um canal oficial respondeu de forma válida (mesmo que sem anúncios)

    async def buscar(self, params: BuscaImovelInput, ao_progredir=None, cancelado=None) -> list[dict]:
        coletados: list[dict] = []
        vistos: set[str] = set()
        async with httpx.AsyncClient(headers=CABECALHOS_MCP, timeout=20.0, follow_redirects=True) as client:
            try:
                await self._por_mcp(client, params, coletados, vistos, ao_progredir, cancelado)
                self.canal_usado = "mcp"
            except MCPErro as e:
                self.diagnostico.append(f"MCP oficial indisponível ({e.categoria}: {e}).")
            if not coletados:
                try:
                    await self._por_busca_texto(client, params, coletados, vistos, ao_progredir)
                    if coletados:
                        self.canal_usado = "well-known/search"
                except Exception as e:  # noqa: BLE001
                    self.diagnostico.append(f"Busca oficial /.well-known/search indisponível ({type(e).__name__}).")
        if not coletados and self.fonte_respondeu:
            self.canal_usado = self.canal_usado or "mcp"
            self.diagnostico.append("Canal oficial respondeu: nenhum anúncio encontrado para este local (não é falha).")
        if not coletados and not self.fonte_respondeu:
            legado = ChavesNaMaoScraper(self.chave_api)
            coletados = await legado.buscar(params, ao_progredir=ao_progredir, cancelado=cancelado)
            self.diagnostico += [f"(páginas públicas) {d}" for d in legado.diagnostico]
            self.canal_usado = "paginas_publicas"
        self._filtrar_local(coletados, params)
        return coletados

    async def _por_mcp(self, client, params, coletados, vistos, ao_progredir, cancelado):
        mcp = ClienteMCP(client)
        try:
            await mcp.iniciar()
        except MCPErro as e:
            if e.categoria in ("conexao", "bloqueio"):
                raise
            # servidor sem estado: segue direto para a chamada
        paginas = min(params.limite_paginas, PAGINA_MAX)
        for pagina in range(1, paginas + 1):
            if cancelado and cancelado():
                self.diagnostico.append(f"Coleta interrompida antes da página {pagina}.")
                break
            r = await chamar_busca(mcp, params, pagina)
            itens, total, formato = itens_do_resultado(r)
            if total is not None:
                self.total_declarado = total
            if pagina == 1:
                self.debug["parser"].append(f"MCP: {formato}, {len(itens)} itens, total declarado {total}")
            if not itens:
                if pagina == 1 and formato == "nao_reconhecido":
                    if isinstance(r.get("structuredContent"), (dict, list)):
                        self.fonte_respondeu = True  # resposta estruturada válida, só sem anúncios para esta consulta
                        self.diagnostico.append("MCP respondeu sem anúncios para esta consulta.")
                    else:
                        raise MCPErro("formato de resposta não reconhecido", "protocolo")
                elif pagina == 1:
                    self.fonte_respondeu = True
                break
            self.fonte_respondeu = True
            novos = 0
            for i in itens:
                if i["url"] and i["url"] in vistos:
                    continue
                vistos.add(i["url"])
                coletados.append(i)
                novos += 1
            if ao_progredir:
                ao_progredir(pagina, coletados)
            if novos == 0 or len(itens) < TAMANHO_MAX:
                break
            await asyncio.sleep(1.0)

    async def _por_busca_texto(self, client, params, coletados, vistos, ao_progredir):
        tipo = TIPOS.get(params.tipo_imovel, "apartamento")
        acao = "para alugar" if params.finalidade == "LOCACAO" else "para comprar"
        local = f"{params.bairro} {params.cidade}".strip()
        q = f"{tipo} {acao} em {local} {params.uf.upper()}"
        resp = await client.get(BUSCA_URL, params={"q": q}, headers={"User-Agent": AGENTE, "Accept": "text/markdown,*/*"})
        if resp.status_code != 200:
            raise MCPErro(f"HTTP {resp.status_code}", "http")
        itens, total, _ = itens_do_resultado({"content": [{"type": "text", "text": resp.text}]})
        if "anúncios encontrados" in resp.text or itens:
            self.fonte_respondeu = True
        self.total_declarado = total if total is not None else self.total_declarado
        for i in itens:
            if i["url"] not in vistos:
                vistos.add(i["url"])
                coletados.append(i)
        if ao_progredir and coletados:
            ao_progredir(1, coletados)

    def _filtrar_local(self, itens: list[dict], params: BuscaImovelInput) -> None:
        """Descarta anúncio cuja cidade de origem foi informada e é outra (match tolerante a acento)."""
        alvo = self._slug(params.cidade)
        antes = len(itens)
        itens[:] = [i for i in itens if not i.get("cidade_origem") or alvo in self._slug(i["cidade_origem"])]
        if antes != len(itens):
            self.diagnostico.append(f"{antes - len(itens)} anúncio(s) descartado(s) por serem de outra cidade.")
