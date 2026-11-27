import httpx
import os
import re
import json
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Optional
from fastapi import Body, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from app import conta
from app.exporter import gerar_csv
from app.models import AmostraMercado, BuscaImovelInput
from app.normalizer import normalizar_registro_bruto
from app.qualidade import avaliar
from app.scrapers.chaves_mcp import ChavesNaMaoMCPScraper
from app.scrapers.olx import OLXScraper

FONTES = {"olx": OLXScraper, "chaves": ChavesNaMaoMCPScraper}


async def coletar_fontes(params, fontes, ao_progredir=None, cancelado=None, chave_api=None):
    """Roda as fontes escolhidas em paralelo; uma fonte com falha não derruba as outras."""
    import asyncio
    escolhidas = [k for k in fontes if k in FONTES] or ["olx"]
    scrapers = [FONTES[k]() for k in escolhidas]
    for sc in scrapers:
        sc.chave_api = chave_api
    por_fonte: dict[str, list[dict]] = {}

    def mk(sc):
        def cb(pagina, lista):
            por_fonte[sc.nome_fonte] = lista
            if ao_progredir:
                ao_progredir(pagina, [i for l in por_fonte.values() for i in l])
        return cb

    resultados = await asyncio.gather(
        *[sc.buscar(params, ao_progredir=mk(sc), cancelado=cancelado) for sc in scrapers], return_exceptions=True
    )
    brutos, diag = [], []
    for sc, r in zip(scrapers, resultados):
        if isinstance(r, Exception):
            diag.append(f"{sc.nome_fonte}: não foi possível consultar agora ({type(r).__name__}).")
            continue
        brutos += r
        diag += [f"{sc.nome_fonte}: {d}" for d in sc.diagnostico]
        diag.append(f"{sc.nome_fonte}: {len(r)} anúncio(s) coletado(s).")
    return brutos, diag

app = FastAPI(title="Inferência Estatística", version="0.2.0")


def chave_valida(texto: str) -> str | None:
    """Aceita só o formato de um token (letras, números, - e _). Nunca é registrada em log."""
    t = (texto or "").strip()
    return t if re.fullmatch(r"[A-Za-z0-9_-]{16,80}", t) else None


@app.get("/canal")
async def canal():
    """Informa se o servidor já tem um canal de coleta próprio (sem precisar da chave da pessoa)."""
    return {"servidor": bool(("".join((os.getenv("OLX_FETCH_TEMPLATE") or "").split())) or os.getenv("OLX_PROXY_URL"))}


def usuario_da(request: Request | None) -> dict | None:
    return conta.ler_sessao(request.cookies.get(conta.COOKIE)) if request is not None else None


async def chave_do_pedido(request: Request, enviada: str = "") -> str | None:
    """Chave enviada pelo navegador ou, se a pessoa estiver logada, a guardada na conta dela."""
    c = chave_valida(enviada)
    if c:
        return c
    u = usuario_da(request)
    return await conta.buscar_chave(u["sub"]) if u else None


@app.get("/auth/config")
async def auth_config(request: Request):
    u = usuario_da(request)
    tem = bool(u and await conta.buscar_chave(u["sub"]))
    return {
        "login": conta.login_disponivel(), "client_id": conta.client_id() if conta.login_disponivel() else "",
        "cofre": conta.cofre_disponivel(), "cofre_motivo": "ok" if conta.cofre_disponivel() else conta.motivo_sem_cofre(), "usuario": {"nome": u["nome"], "email": u["email"]} if u else None, "tem_chave": tem,
    }


@app.post("/auth/google")
async def auth_google(credential: str = Form("")):
    u = await conta.verificar_google(credential)
    if not u:
        return JSONResponse({"ok": False, "erro": "Não foi possível confirmar o login com o Google."}, status_code=401)
    resp = JSONResponse({"ok": True, "usuario": {"nome": u["nome"], "email": u["email"]}, "tem_chave": bool(await conta.buscar_chave(u["sub"]))})
    resp.set_cookie(conta.COOKIE, conta.criar_sessao(u), max_age=conta.DURACAO, httponly=True, secure=True, samesite="lax")
    return resp


@app.post("/auth/sair")
async def auth_sair():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(conta.COOKIE)
    return resp


@app.post("/chave/remover")
async def remover_chave_conta(request: Request):
    u = usuario_da(request)
    return {"ok": await conta.remover_chave(u["sub"]) if u else False}


@app.post("/chave/validar")
async def validar_chave(request: Request, chave: str = Form("")):
    """Testa a chave do ScrapingAnt consultando só o saldo de créditos. Não guarda nada no servidor."""
    c = chave_valida(chave)
    if not c:
        return {"ok": False, "erro": "Isto não parece uma chave do ScrapingAnt. Copie o campo “API token” do painel."}
    try:
        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.get("https://api.scrapingant.com/v2/usage", params={"x-api-key": c})
    except Exception:
        return {"ok": False, "incerto": True, "erro": "Não consegui falar com o ScrapingAnt agora. Tente de novo em instantes."}
    if r.status_code in (401, 403, 422):
        return {"ok": False, "erro": "O ScrapingAnt não reconheceu esta chave. Confira se copiou o token inteiro."}
    if r.status_code != 200:
        return {"ok": False, "incerto": True, "erro": "O ScrapingAnt não respondeu como esperado. Tente de novo em instantes."}
    try:
        j = r.json()
    except ValueError:
        j = {}
    u = usuario_da(request)
    guardada = await conta.guardar_chave(u["sub"], u["email"], c) if u else False
    return {"ok": True, "restantes": j.get("remained_credits"), "total": j.get("plan_total_credits"), "na_conta": guardada}
templates = Jinja2Templates(directory="templates")


def _brl(v) -> str:
    """1234567.0 -> '1.234.567' (sem casas decimais; valores monetários inteiros em reais)."""
    try:
        return f"{round(float(v)):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "–"


def _num(v) -> str:
    """98.0 -> '98'; 52.68 -> '52,68'."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "–"
    return (f"{f:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


templates.env.filters["brl"] = _brl
templates.env.filters["num"] = _num

ULTIMA_COLETA: list[AmostraMercado] = []
ULTIMA_META: dict = {}  # parâmetros e metadados da coleta que gerou ULTIMA_COLETA (nunca mostrar amostras sem eles)


def avaliar_grau_nbr14653(total_validas: int) -> str:
    if total_validas >= 15:
        return "Atinge mínimo amostral para Grau III (≥ 15 dados, verificar relação com nº de variáveis)."
    if total_validas >= 10:
        return "Atinge mínimo amostral para Grau II (≥ 10 dados)."
    if total_validas >= 5:
        return "Atinge mínimo amostral para Grau I (≥ 5 dados)."
    return "Abaixo do mínimo de 5 dados da NBR 14653-2. Amplie o raio ou páginas de busca."


def normalizar_lista(brutos: list[dict], params: BuscaImovelInput) -> list[AmostraMercado]:
    normalizados: list[AmostraMercado] = []
    vistos_assinatura: set[tuple] = set()
    for item in brutos:
        amostra = normalizar_registro_bruto(
            idx=len(normalizados) + 1,
            raw=item,
            uf=params.uf,
            cidade=params.cidade,
            tipo_imovel=params.tipo_imovel,
            finalidade=params.finalidade,
        )
        amostra.fora_filtros, amostra.motivos, amostra.completude = avaliar(
            amostra, params, f"{item.get('titulo', '')} {item.get('detalhes', '')}"
        )
        # Duplicidade: mesmo endereço do anúncio, ou mesma combinação bairro+área+preço+quartos (só quando há área e preço)
        chaves_dup = []
        if amostra.url_anuncio:
            chaves_dup.append(("url", amostra.url_anuncio.split("?")[0].rstrip("/")))
        if amostra.area_m2 and amostra.valor_oferta and amostra.bairro != "NAO_INFORMADO":
            chaves_dup.append(("sig", amostra.bairro.lower(), amostra.area_m2, amostra.valor_oferta, amostra.quartos))
        if any(k in vistos_assinatura for k in chaves_dup):
            continue
        vistos_assinatura.update(chaves_dup)
        normalizados.append(amostra)
    return normalizados


def _meta_coleta(inicio: float, fontes: list[str]) -> dict:
    import time as _time
    nomes = {"olx": "OLX", "chaves": "Chaves na Mão"}
    return {"quando": _time.strftime("%d/%m %H:%M", _time.gmtime(inicio - 3 * 3600)),  # horário de Brasília
            "fontes": " + ".join(nomes.get(f, f) for f in fontes)}


def _resposta_resultado(request: Request, normalizados, params, diagnostico, coleta_ativa=None, meta=None):
    validas = sum(1 for a in normalizados if a.alerta_saneamento == "OK")
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "amostras": normalizados,
            "status_nbr": avaliar_grau_nbr14653(validas),
            "filtros": params.model_dump(),
            "diagnostico": diagnostico,
            "coleta_ativa": coleta_ativa,
            "meta": meta,
        },
    )


JOBS: dict[str, dict] = {}


async def _rodar_job(job_id: str):
    job = JOBS[job_id]

    def progresso(pagina: int, coletados: list[dict]):
        job["pagina"] = pagina
        job["encontrados"] = len(coletados)
        job["parcial"] = list(coletados)
        job["previa"] = [
            {"titulo": (c.get("titulo") or "")[:70], "preco": c.get("preco") or ""} for c in coletados[-5:]
        ]

    try:
        brutos, diag = await coletar_fontes(job["params"], job["fontes"], ao_progredir=progresso, cancelado=lambda: job["cancelar"], chave_api=job.get("chave"))
        job["resultado"] = normalizar_lista(brutos, job["params"])
        job["diagnostico"] = diag
        job["estado"] = "interrompida" if job["cancelar"] else "concluida"
    except Exception as exc:  # noqa: BLE001
        job["estado"] = "erro"
        job["erro"] = f"Falha na coleta ({type(exc).__name__}). Tente novamente."


@app.post("/coleta")
async def iniciar_coleta(
    request: Request,
    uf: str = Form(...), cidade: str = Form(...), bairro: str = Form(""), finalidade: str = Form("VENDA"),
    tipo_imovel: str = Form("APARTAMENTO"), area_min: Optional[str] = Form(None), area_max: Optional[str] = Form(None),
    quartos_min: Optional[str] = Form(None), preco_min: Optional[str] = Form(None), preco_max: Optional[str] = Form(None),
    limite_paginas: int = Form(2),
    fontes: list[str] = Form(default=["olx", "chaves"]),
    chave: str = Form(""),
):
    import asyncio
    import time
    import uuid

    try:
        params = BuscaImovelInput(
            uf=uf, cidade=cidade, bairro=bairro, finalidade=finalidade, tipo_imovel=tipo_imovel,  # type: ignore
            area_min=float(area_min) if area_min else None, area_max=float(area_max) if area_max else None,
            quartos_min=int(quartos_min) if quartos_min else None,
            preco_min=float(preco_min) if preco_min else None, preco_max=float(preco_max) if preco_max else None,
            limite_paginas=limite_paginas,
        )
    except Exception:
        return JSONResponse({"erro": "Confira os campos informados (UF com 2 letras e cidade)."}, status_code=422)
    for antigo in [k for k, j in JOBS.items() if time.time() - j["inicio"] > 3600]:
        JOBS.pop(antigo, None)
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "params": params, "fontes": fontes, "estado": "rodando", "pagina": 0, "encontrados": 0,
        "chave": await chave_do_pedido(request, chave), "previa": [], "parcial": [], "cancelar": False, "resultado": None, "diagnostico": [], "erro": "", "inicio": time.time(),
    }
    JOBS[job_id]["tarefa"] = asyncio.create_task(_rodar_job(job_id))
    return {"id": job_id}


@app.get("/coleta/{job_id}")
async def status_coleta(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        return JSONResponse({"erro": "Coleta não encontrada (o servidor pode ter reiniciado)."}, status_code=404)
    import time
    return {
        "estado": j["estado"], "pagina": j["pagina"], "paginas": j["params"].limite_paginas,
        "encontrados": j["encontrados"], "fontes": len(j["fontes"]), "previa": j["previa"], "erro": j["erro"],
        "segundos": int(time.time() - j["inicio"]),
    }


@app.post("/coleta/{job_id}/cancelar")
async def cancelar_coleta(job_id: str):
    j = JOBS.get(job_id)
    if j:
        j["cancelar"] = True
    return {"ok": bool(j)}


@app.get("/coleta/{job_id}/resultado", response_class=HTMLResponse)
async def resultado_coleta(request: Request, job_id: str):
    global ULTIMA_COLETA
    j = JOBS.get(job_id)
    if not j:
        return RedirectResponse("/", status_code=303)
    if j["resultado"] is not None:
        ULTIMA_COLETA = j["resultado"]
        diag, ativa = j["diagnostico"], None
    elif j["parcial"]:
        ULTIMA_COLETA = normalizar_lista(list(j["parcial"]), j["params"])
        diag, ativa = [], {"id": job_id, "n": j["encontrados"]}
    else:
        return RedirectResponse("/", status_code=303)
    meta = _meta_coleta(j["inicio"], j["fontes"])
    ULTIMA_META.clear()
    ULTIMA_META.update({"params": j["params"].model_dump(), "meta": meta})
    return _resposta_resultado(request, ULTIMA_COLETA, j["params"], diag, ativa, meta)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "amostras": ULTIMA_COLETA,
            "status_nbr": avaliar_grau_nbr14653(
                sum(1 for a in ULTIMA_COLETA if a.alerta_saneamento == "OK")
            )
            if ULTIMA_COLETA
            else None,
            # amostras sempre acompanhadas dos parâmetros da coleta que as gerou (antes: filtros vazios)
            "filtros": ULTIMA_META.get("params", {}) if ULTIMA_COLETA else {},
            "meta": ULTIMA_META.get("meta") if ULTIMA_COLETA else None,
        },
    )


@app.get("/debug-olx")
async def debug_olx(
    request: Request,
    uf: str = "PE",
    cidade: str = "Recife",
    bairro: str = "",
    tipo_imovel: str = "APARTAMENTO",
    finalidade: str = "VENDA",
):
    """Diagnóstico medido (JSON): código HTTP, tempo, bytes, dados estruturados e sinais de bloqueio.
    Faz 1 requisição por canal, sem retentativas. Se a pessoa estiver logada com chave guardada, compara os canais."""
    from app.diagnostico import diagnosticar

    params = BuscaImovelInput(
        uf=uf, cidade=cidade, bairro=bairro,
        finalidade=finalidade,  # type: ignore
        tipo_imovel=tipo_imovel,  # type: ignore
        limite_paginas=1,
    )
    return JSONResponse(await diagnosticar(params, await chave_do_pedido(request)))


_DIAG_FONTES = {"t": 0.0, "res": None}


@app.get("/diagnostico-fontes")
async def diagnostico_fontes(uf: str = "PE", cidade: str = "Recife", tipo_imovel: str = "APARTAMENTO", finalidade: str = "VENDA"):
    """Diagnóstico de fontes (somente leitura): mede, deste servidor, o que cada fonte devolve e quanto custa em memória/CPU.
    Uma requisição por recurso, sem proxy e sem disfarce; respeita o robots.txt. Resultado guardado por 2 minutos para não
    repetir pedidos às fontes."""
    import time as _t
    from app.diag_fontes import diagnosticar_fontes

    if not re.fullmatch(r"[A-Za-z]{2}", uf) or not (2 <= len(cidade) <= 60) or tipo_imovel not in ("APARTAMENTO", "CASA", "TERRENO", "COMERCIAL") or finalidade not in ("VENDA", "LOCACAO"):
        return JSONResponse({"erro": "parâmetros inválidos"}, status_code=400)
    chave = (uf.upper(), cidade.strip().lower(), tipo_imovel, finalidade)
    agora = _t.time()
    c = _DIAG_FONTES
    if c["res"] is not None and c.get("chave") == chave and agora - c["t"] < 120:
        return JSONResponse({**c["res"], "do_cache_ha_segundos": int(agora - c["t"])})
    if agora - c["t"] < 20:
        return JSONResponse({"erro": "aguarde alguns segundos entre diagnósticos"}, status_code=429)
    c["t"] = agora
    params = BuscaImovelInput(uf=uf.upper(), cidade=cidade.strip(), bairro="", finalidade=finalidade,  # type: ignore
                              tipo_imovel=tipo_imovel, limite_paginas=1)  # type: ignore
    res = await diagnosticar_fontes(params)
    c.update({"res": res, "chave": chave, "t": _t.time()})
    return JSONResponse(res)


_VALIDACAO: dict = {"estado": "ocioso"}


@app.get("/validacao-nacional")
async def validacao_nacional(iniciar: int = 0, cidades: str = "", tipo_imovel: str = "APARTAMENTO", finalidade: str = "VENDA", paginas: int = 2):
    """Validação medida em várias cidades (fonte Chaves na Mão via MCP oficial). `?iniciar=1` dispara em segundo plano;
    sem parâmetro mostra o andamento/resultado. Formato de `cidades`: "Manaus-AM;Recife-PE"."""
    import asyncio
    import time as _t
    from app.validacao import CIDADES_PADRAO, validar

    if iniciar:
        if _VALIDACAO.get("estado") == "rodando":
            return JSONResponse({**{k: v for k, v in _VALIDACAO.items() if k != "tarefa"}, "aviso": "já em andamento"})
        if _VALIDACAO.get("estado") == "concluido" and _t.time() - _VALIDACAO.get("inicio", 0) < 300:
            return JSONResponse({**{k: v for k, v in _VALIDACAO.items() if k != "tarefa"}, "aviso": "resultado recente mantido por 5 minutos"})
        lista = []
        if cidades.strip():
            for par in cidades.split(";"):
                nome, _, uf = par.strip().rpartition("-")
                if re.fullmatch(r"[A-Za-z]{2}", uf) and 2 <= len(nome) <= 60:
                    lista.append((uf.upper(), nome.strip()))
        lista = (lista or CIDADES_PADRAO)[:14]
        if tipo_imovel not in ("APARTAMENTO", "CASA", "TERRENO", "COMERCIAL") or finalidade not in ("VENDA", "LOCACAO"):
            return JSONResponse({"erro": "parâmetros inválidos"}, status_code=400)
        _VALIDACAO.clear()
        _VALIDACAO.update({"estado": "rodando", "inicio": _t.time(), "concluidas": 0, "total": len(lista), "cidades": []})
        _VALIDACAO["tarefa"] = asyncio.create_task(validar(_VALIDACAO, lista, tipo_imovel, finalidade, max(1, min(paginas, 5))))
    return JSONResponse({k: v for k, v in _VALIDACAO.items() if k != "tarefa"})


@app.get("/buscar")
async def buscar_get():
    return RedirectResponse(url="/", status_code=303)


@app.post("/buscar", response_class=HTMLResponse)
async def executar_busca(
    request: Request,
    uf: str = Form(...),
    cidade: str = Form(...),
    bairro: str = Form(""),
    finalidade: str = Form("VENDA"),
    tipo_imovel: str = Form("APARTAMENTO"),
    area_min: Optional[str] = Form(None),
    area_max: Optional[str] = Form(None),
    quartos_min: Optional[str] = Form(None),
    preco_min: Optional[str] = Form(None),
    preco_max: Optional[str] = Form(None),
    limite_paginas: int = Form(2),
    fontes: list[str] = Form(default=["olx", "chaves"]),
):
    global ULTIMA_COLETA

    params = BuscaImovelInput(
        uf=uf,
        cidade=cidade,
        bairro=bairro,
        finalidade=finalidade,  # type: ignore
        tipo_imovel=tipo_imovel,  # type: ignore
        area_min=float(area_min) if area_min else None,
        area_max=float(area_max) if area_max else None,
        quartos_min=int(quartos_min) if quartos_min else None,
        preco_min=float(preco_min) if preco_min else None,
        preco_max=float(preco_max) if preco_max else None,
        limite_paginas=limite_paginas,
    )

    import time as _t
    brutos, diag = await coletar_fontes(params, fontes)
    ULTIMA_COLETA = normalizar_lista(brutos, params)
    meta = _meta_coleta(_t.time(), fontes)
    ULTIMA_META.clear()
    ULTIMA_META.update({"params": params.model_dump(), "meta": meta})
    return _resposta_resultado(request, ULTIMA_COLETA, params, diag, None, meta)


# ---------------------------------------------------------------------------------------------
# API da estação de trabalho (cálculo sem estado: o servidor não guarda nada; o projeto fica com o usuário)
# ---------------------------------------------------------------------------------------------

def _registros_de(amostras) -> list[dict]:
    from app.modelagem import registro_de_amostra
    return [registro_de_amostra(a) for a in amostras]


@app.get("/coleta/{job_id}/amostras.json")
async def amostras_json(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        return JSONResponse({"erro": "Coleta não encontrada (o servidor reinicia e esquece coletas antigas; exporte o projeto para guardá-la)."}, status_code=404)
    lista = j["resultado"] if j["resultado"] is not None else normalizar_lista(list(j["parcial"]), j["params"])
    return {"id": job_id, "parametros": j["params"].model_dump(), "meta": _meta_coleta(j["inicio"], j["fontes"]), "estado": j["estado"],
            "amostras": _registros_de(lista), "diagnostico": j.get("diagnostico", [])}


@app.get("/api/amostras-atuais")
async def amostras_atuais():
    return {"parametros": ULTIMA_META.get("params", {}), "meta": ULTIMA_META.get("meta"), "amostras": _registros_de(ULTIMA_COLETA)}


def _json_corpo(corpo) -> dict:
    return corpo if isinstance(corpo, dict) else {}


@app.post("/api/matriz")
async def api_matriz(corpo: dict = Body(...)):
    from app.modelagem import EspecificacaoInvalida, montar_matriz
    try:
        return montar_matriz(corpo.get("registros") or [], corpo.get("variaveis") or [], corpo.get("ids_usados"))
    except EspecificacaoInvalida as e:
        return JSONResponse({"erro": str(e)}, status_code=422)


@app.post("/api/modelo")
async def api_modelo(corpo: dict = Body(...)):
    from app.modelagem import EspecificacaoInvalida, ajustar_modelo
    try:
        return ajustar_modelo(corpo.get("registros") or [], corpo.get("variaveis") or [], corpo.get("ids_usados"),
                              corpo.get("avaliando"), float(corpo.get("nivel_confianca") or 0.80))
    except (EspecificacaoInvalida, ValueError) as e:
        return JSONResponse({"erro": str(e)}, status_code=422)


@app.post("/api/exploratoria")
async def api_exploratoria(corpo: dict = Body(...)):
    from app.modelagem import exploratoria
    return exploratoria(corpo.get("registros") or [], corpo.get("numericas") or [], corpo.get("categoricas") or [])


@app.get("/api/suficiencia")
async def api_suficiencia(n_coletados: int = 0, n_utilizaveis: int = 0, k: int = 0, n_ausentes: int = 0):
    from app.estatistica import suficiencia
    if min(n_coletados, n_utilizaveis, k, n_ausentes) < 0 or k > 100:
        return JSONResponse({"erro": "valores inválidos"}, status_code=422)
    return suficiencia(n_coletados, n_utilizaveis, k, n_ausentes)


FOTOS_CACHE: dict[int, list[str]] = {}


@app.get("/fotos/{id_amostra}")
async def fotos_amostra(id_amostra: int, request: Request):
    """Carrega a galeria completa de um anúncio sob demanda (com cache; não bloqueia a coleta)."""
    amostra = next((a for a in ULTIMA_COLETA if a.id_amostra == id_amostra), None)
    if amostra is None:
        return JSONResponse({"fotos": [], "erro": "Amostra não encontrada."}, status_code=404)
    if id_amostra in FOTOS_CACHE:
        return {"fotos": FOTOS_CACHE[id_amostra], "cache": True}
    try:
        fotos = await OLXScraper(await chave_do_pedido(request, request.headers.get("x-chave-api", ""))).fotos_do_anuncio(amostra.url_anuncio)
    except Exception:
        fotos = []
    if not fotos:
        return {"fotos": amostra.fotos, "aviso": "Não foi possível carregar mais fotos agora. Tente novamente em instantes."}
    FOTOS_CACHE[id_amostra] = fotos
    return {"fotos": fotos}


def aplicar_correcoes(amostras: list[AmostraMercado], bruto: str) -> None:
    """Aplica as correções feitas pelo avaliador na tela (valor, área, quartos) antes de exportar."""
    try:
        dados = json.loads(bruto) if bruto else {}
    except ValueError:
        return
    if not isinstance(dados, dict):
        return
    for a in amostras:
        c = dados.get(str(a.id_amostra))
        if not isinstance(c, dict):
            continue

        def num(x):
            return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 else None

        if "valor" in c:
            a.valor_oferta = num(c["valor"])
        if "area" in c:
            a.area_m2 = num(c["area"])
        if "q" in c:
            q = num(c["q"])
            a.quartos = int(q) if q is not None else None
        a.valor_m2 = round(a.valor_oferta / a.area_m2, 2) if a.valor_oferta and a.area_m2 else None


@app.post("/exportar-csv")
async def exportar_csv(
    ids_selecionados: list[int] = Form(default=[]),
    modo: str = Form(default="completo"),
    correcoes: str = Form(default=""),
):
    selecionadas = [
        a.model_copy(deep=True)
        for a in ULTIMA_COLETA
        if not ids_selecionados or a.id_amostra in ids_selecionados
    ]
    aplicar_correcoes(selecionadas, correcoes)
    apenas_numericas = modo == "numerico"
    conteudo_csv = gerar_csv(selecionadas, apenas_numericas=apenas_numericas)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    nome_arquivo = f"amostras_{modo}_{timestamp}.csv"

    return Response(
        content=conteudo_csv.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
