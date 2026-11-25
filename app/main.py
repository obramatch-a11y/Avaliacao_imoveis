from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from app.exporter import gerar_csv_sisdea
from app.models import AmostraSISDEA, BuscaImovelInput
from app.normalizer import normalizar_registro_bruto
from app.scrapers.olx import OLXScraper

app = FastAPI(title="Coletor SISDEA Web", version="0.1.0")
templates = Jinja2Templates(directory="templates")

ULTIMA_COLETA: list[AmostraSISDEA] = []


def avaliar_grau_nbr14653(total_validas: int) -> str:
    if total_validas >= 15:
        return "Atinge mínimo amostral para Grau III (≥ 15 dados, verificar relação com nº de variáveis)."
    if total_validas >= 10:
        return "Atinge mínimo amostral para Grau II (≥ 10 dados)."
    if total_validas >= 5:
        return "Atinge mínimo amostral para Grau I (≥ 5 dados)."
    return "Abaixo do mínimo de 5 dados da NBR 14653-2. Amplie o raio ou páginas de busca."


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
    limite_paginas: int = Form(2),
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
        limite_paginas=limite_paginas,
    )

    scraper = OLXScraper()
    brutos = await scraper.buscar(params)

    normalizados: list[AmostraSISDEA] = []
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
        assinatura = (
            amostra.bairro.lower(),
            amostra.area_m2,
            amostra.valor_oferta,
            amostra.quartos,
        )
        if assinatura in vistos_assinatura:
            continue
        vistos_assinatura.add(assinatura)
        normalizados.append(amostra)

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


@app.post("/exportar-csv")
async def exportar_csv(
    ids_selecionados: list[int] = Form(default=[]),
    modo: str = Form(default="completo"),
):
    selecionadas = [
        a for a in ULTIMA_COLETA if not ids_selecionados or a.id_amostra in ids_selecionados
    ]
    apenas_numericas = modo == "numerico"
    conteudo_csv = gerar_csv_sisdea(selecionadas, apenas_numericas=apenas_numericas)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    nome_arquivo = f"amostra_sisdea_{modo}_{timestamp}.csv"

    return Response(
        content=conteudo_csv.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
