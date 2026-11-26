import httpx
import os
import re
import json
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from app.exporter import gerar_csv
from app.models import AmostraMercado, BuscaImovelInput
from app.normalizer import normalizar_registro_bruto
from app.qualidade import avaliar
from app.scrapers.chaves import ChavesNaMaoScraper
from app.scrapers.olx import OLXScraper

FONTES = {"olx": OLXScraper, "chaves": ChavesNaMaoScraper}


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


@app.post("/chave/validar")
async def validar_chave(chave: str = Form("")):
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
    return {"ok": True, "restantes": j.get("remained_credits"), "total": j.get("plan_total_credits")}
templates = Jinja2Templates(directory="templates")

ULTIMA_COLETA: list[AmostraMercado] = []


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
        assinatura = (amostra.bairro.lower(), amostra.area_m2, amostra.valor_oferta, amostra.quartos)
        if assinatura in vistos_assinatura:
            continue
        vistos_assinatura.add(assinatura)
        normalizados.append(amostra)
    return normalizados


def _resposta_resultado(request: Request, normalizados, params, diagnostico, coleta_ativa=None):
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
        "chave": chave_valida(chave), "previa": [], "parcial": [], "cancelar": False, "resultado": None, "diagnostico": [], "erro": "", "inicio": time.time(),
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
    resp = _resposta_resultado(request, ULTIMA_COLETA, j["params"], diag, ativa)
    return resp


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
            "filtros": {},
        },
    )


@app.get("/debug-olx")
async def debug_olx(
    uf: str = "PE",
    cidade: str = "Jaboatão dos Guararapes",
    bairro: str = "",
    tipo_imovel: str = "APARTAMENTO",
    finalidade: str = "VENDA",
):
    """Diagnóstico: mostra o que o OLX devolveu e como o app leu os campos (1 página)."""
    params = BuscaImovelInput(
        uf=uf, cidade=cidade, bairro=bairro,
        finalidade=finalidade,  # type: ignore
        tipo_imovel=tipo_imovel,  # type: ignore
        limite_paginas=1,
    )
    scraper = OLXScraper()
    brutos = await scraper.buscar(params)
    normalizados = normalizar_lista(brutos, params)

    ULTIMA_COLETA = normalizados
    validas = sum(1 for a in normalizados if a.alerta_saneamento == "OK")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "amostras": normalizados,
            "status_nbr": avaliar_grau_nbr14653(validas),
            "filtros": params.model_dump(),
            "diagnostico": scraper.diagnostico,
        },
    )


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

    brutos, diag = await coletar_fontes(params, fontes)
    ULTIMA_COLETA = normalizar_lista(brutos, params)
    return _resposta_resultado(request, ULTIMA_COLETA, params, diag)


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
        fotos = await OLXScraper(chave_valida(request.headers.get("x-chave-api", ""))).fotos_do_anuncio(amostra.url_anuncio)
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
