"""Validação nacional medida: roda a busca da fonte Chaves na Mão (MCP oficial) por cidade e mede cobertura,
tempo, memória/CPU e completude. Nada é inventado: cada número vem da execução real no servidor."""
import statistics
import time

from app.diag_fontes import Medidor, _cgroup_mb, _pico_mb, _rss_mb
from app.models import BuscaImovelInput
from app.normalizer import normalizar_registro_bruto
from app.scrapers.chaves_mcp import ChavesNaMaoMCPScraper

CIDADES_PADRAO = [
    ("AM", "Manaus"), ("PE", "Recife"), ("AL", "Maceió"), ("PE", "Caruaru"), ("GO", "Goiânia"),
    ("SP", "São Paulo"), ("PR", "Curitiba"),
    # municípios pequenos (a existência de anúncios em cada um é justamente o que se mede)
    ("MG", "Tiradentes"), ("GO", "Pirenópolis"), ("AM", "Presidente Figueiredo"), ("PE", "Bonito"), ("AL", "Marechal Deodoro"),
]

CAMPOS = ("preco", "area", "quartos", "banheiros", "vagas", "bairro", "url", "fotos")


def cobertura_percentual(brutos: list[dict]) -> dict:
    n = len(brutos)
    if not n:
        return {}
    return {c: round(100 * sum(1 for i in brutos if i.get(c)) / n) for c in CAMPOS}


async def validar_cidade(uf: str, cidade: str, tipo: str, finalidade: str, paginas: int) -> dict:
    params = BuscaImovelInput(uf=uf, cidade=cidade, bairro="", finalidade=finalidade, tipo_imovel=tipo, limite_paginas=paginas)  # type: ignore
    sc = ChavesNaMaoMCPScraper()
    m = Medidor()
    erro = ""
    try:
        brutos = await sc.buscar(params)
    except Exception as exc:  # noqa: BLE001
        brutos, erro = [], f"{type(exc).__name__}: {str(exc)[:120]}"
    med = m.fechar()
    amostras = [normalizar_registro_bruto(i + 1, b, uf, cidade, tipo, finalidade) for i, b in enumerate(brutos)]
    m2 = [a.valor_m2 for a in amostras if a.valor_m2]
    return {
        "uf": uf, "cidade": cidade, "canal": sc.canal_usado or "nenhum", "total_declarado_pela_fonte": sc.total_declarado,
        "anuncios_coletados": len(brutos), "com_valor_m2": len(m2),
        "valor_m2_mediana": round(statistics.median(m2)) if m2 else None,
        "valor_m2_min_max": [round(min(m2)), round(max(m2))] if m2 else None,
        "alertas_de_saneamento": sum(1 for a in amostras if a.alerta_saneamento != "OK"),
        "cobertura_campos_pct": cobertura_percentual(brutos), **med,
        "erro": erro, "diagnostico": sc.diagnostico[:6],
        "classificacao": "FALHA" if erro else ("OK" if brutos else "SEM_ANUNCIOS_OU_NAO_LIDO"),
    }


async def validar(estado: dict, cidades, tipo: str, finalidade: str, paginas: int = 2) -> None:
    import asyncio
    estado.update({"estado": "rodando", "inicio": time.time(), "concluidas": 0, "total": len(cidades), "cidades": []})
    estado["ambiente_inicio"] = {"memoria_mb": _rss_mb(), "conteiner": _cgroup_mb()}
    for uf, cid in cidades:
        try:
            resultado = await validar_cidade(uf, cid, tipo, finalidade, paginas)
        except Exception as exc:  # noqa: BLE001
            resultado = {"uf": uf, "cidade": cid, "classificacao": "FALHA", "erro": f"{type(exc).__name__}: {str(exc)[:160]}", "tempo_ms": 0}
        estado["cidades"].append(resultado)
        estado["concluidas"] += 1
        await asyncio.sleep(1.0)
    ok = [c for c in estado["cidades"] if c["classificacao"] == "OK"]
    estado["resumo"] = {
        "cidades_com_anuncios": len(ok), "cidades_testadas": len(estado["cidades"]),
        "tempo_total_s": round(time.time() - estado["inicio"], 1),
        "pico_memoria_processo_mb": _pico_mb(), "memoria_processo_fim_mb": _rss_mb(), "conteiner_fim": _cgroup_mb(),
        "tempo_medio_por_cidade_ms": round(statistics.mean(c.get("tempo_ms", 0) for c in estado["cidades"])) if estado["cidades"] else None,
    }
    estado["estado"] = "concluido"
