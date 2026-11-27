"""Matriz de modelagem e ajuste de modelos a partir da base amostral validada.

Regras de método (briefing do avaliador):
- categorias nominais (ex.: bairro) NUNCA recebem códigos numéricos arbitrários: só variáveis indicadoras
  (dummies) com categoria de referência explícita;
- códigos ordinais só com mapa informado pelo avaliador;
- nenhum dado é descartado automaticamente por "ser diferente": só entram na matriz as amostras selecionadas e
  completas nas variáveis do modelo; as demais aparecem listadas com o motivo;
- tudo é determinístico e reproduzível: a matriz recebe uma assinatura (hash) da especificação + dados.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from app import estatistica as E

TIPOS = {"continua", "discreta", "nominal", "ordinal", "dicotomica", "derivada", "proxy", "geografica"}
PAPEIS = {"dependente", "independente", "ignorar"}
TRANSFORMACOES = {"nenhuma", "ln", "raiz", "inversa", "quadrado"}


class EspecificacaoInvalida(ValueError):
    pass


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return float(v) if isinstance(v, bool) else None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _transforma(x: float, t: str) -> float | None:
    if t == "nenhuma":
        return x
    if t == "ln":
        return math.log(x) if x > 0 else None
    if t == "raiz":
        return math.sqrt(x) if x >= 0 else None
    if t == "inversa":
        return 1.0 / x if x != 0 else None
    if t == "quadrado":
        return x * x
    raise EspecificacaoInvalida(f"transformação desconhecida: {t}")


def _valor_bruto(reg: dict, var: dict) -> Any:
    if var.get("tipo") == "derivada":
        d = var.get("derivada") or {}
        a, b = _num(reg.get(d.get("a"))), _num(reg.get(d.get("b")))
        if a is None or b is None:
            return None
        op = d.get("op")
        if op == "+": return a + b
        if op == "-": return a - b
        if op == "*": return a * b
        if op == "/": return a / b if b != 0 else None
        raise EspecificacaoInvalida(f"operação inválida na variável derivada {var.get('nome')}: {op}")
    return reg.get(var.get("campo") or var.get("tecnico") or var.get("nome"))


def validar_especificacao(variaveis: list[dict]) -> None:
    deps = [v for v in variaveis if v.get("papel") == "dependente"]
    if len(deps) != 1:
        raise EspecificacaoInvalida("defina exatamente uma variável dependente")
    nomes = set()
    for v in variaveis:
        nm = v.get("nome")
        if not nm or nm in nomes:
            raise EspecificacaoInvalida(f"nome de variável ausente ou repetido: {nm!r}")
        nomes.add(nm)
        if v.get("tipo") not in TIPOS:
            raise EspecificacaoInvalida(f"{nm}: tipo inválido ({v.get('tipo')})")
        if v.get("papel") not in PAPEIS:
            raise EspecificacaoInvalida(f"{nm}: papel inválido ({v.get('papel')})")
        if v.get("transformacao", "nenhuma") not in TRANSFORMACOES:
            raise EspecificacaoInvalida(f"{nm}: transformação inválida")
        if v["tipo"] == "nominal":
            if v.get("codificacao", "indicadoras") != "indicadoras":
                raise EspecificacaoInvalida(f"{nm}: variável nominal só admite codificação por variáveis indicadoras (sem códigos numéricos arbitrários)")
            if v["papel"] == "dependente":
                raise EspecificacaoInvalida(f"{nm}: variável nominal não pode ser dependente")
        if v["tipo"] == "ordinal" and v["papel"] != "ignorar":
            mapa = v.get("mapa") or {}
            if not mapa or not v.get("justificativa"):
                raise EspecificacaoInvalida(f"{nm}: variável ordinal exige mapa de códigos e justificativa técnica informados pelo avaliador")
        if v["tipo"] == "derivada" and not (v.get("derivada") or {}).get("a"):
            raise EspecificacaoInvalida(f"{nm}: variável derivada exige a origem (campo a, operação e campo b)")


def montar_matriz(registros: list[dict], variaveis: list[dict], ids_usados: list[Any] | None = None, limiar_redundancia: float = 0.9) -> dict:
    """Constrói a matriz do modelo. `registros`: dicts com 'id' e os campos de origem; `ids_usados`: amostras selecionadas."""
    validar_especificacao(variaveis)
    usados = set(ids_usados) if ids_usados is not None else None
    base = [r for r in registros if usados is None or r.get("id") in usados]
    dep = next(v for v in variaveis if v["papel"] == "dependente")
    indep = [v for v in variaveis if v["papel"] == "independente"]

    # categorias das nominais (somente entre registros selecionados)
    colunas_x: list[dict] = []
    for v in indep:
        if v["tipo"] == "nominal":
            cont: dict[str, int] = {}
            for r in base:
                val = _valor_bruto(r, v)
                if val not in (None, ""):
                    cont[str(val)] = cont.get(str(val), 0) + 1
            if not cont:
                continue
            ref = v.get("referencia") or max(sorted(cont), key=lambda c: cont[c])
            if ref not in cont:
                raise EspecificacaoInvalida(f"{v['nome']}: categoria de referência '{ref}' não existe na amostra selecionada")
            for cat in sorted(cont):
                if cat != ref:
                    colunas_x.append({"nome": f"{v['nome']}={cat}", "origem": v["nome"], "tipo": "indicadora", "categoria": cat,
                                      "referencia": ref, "n_categoria": cont[cat]})
        else:
            colunas_x.append({"nome": v["nome"], "origem": v["nome"], "tipo": v["tipo"], "var": v})

    linhas, excluidos = [], []
    ausentes: dict[str, int] = {}
    for r in base:
        y_raw = _num(_valor_bruto(r, dep))
        y = _transforma(y_raw, dep.get("transformacao", "nenhuma")) if y_raw is not None else None
        motivos = []
        if y is None:
            motivos.append(f"{dep['nome']} ausente ou fora do domínio da transformação")
        xs: dict[str, float] = {}
        for c in colunas_x:
            if c["tipo"] == "indicadora":
                bruto = _valor_bruto(r, next(v for v in indep if v["nome"] == c["origem"]))
                if bruto in (None, ""):
                    motivos.append(f"{c['origem']} ausente"); ausentes[c["origem"]] = ausentes.get(c["origem"], 0) + 1
                    break
                xs[c["nome"]] = 1.0 if str(bruto) == c["categoria"] else 0.0
                continue
            v = c["var"]
            bruto = _valor_bruto(r, v)
            if v["tipo"] == "ordinal":
                bruto = (v.get("mapa") or {}).get(str(bruto))
            x = _num(bruto)
            x = _transforma(x, v.get("transformacao", "nenhuma")) if x is not None else None
            if x is None:
                motivos.append(f"{v['nome']} ausente ou fora do domínio da transformação")
                ausentes[v["nome"]] = ausentes.get(v["nome"], 0) + 1
                continue
            xs[c["nome"]] = x
        if motivos or len(xs) != len(colunas_x):
            if not motivos:
                motivos.append("variável independente incompleta")
            excluidos.append({"id": r.get("id"), "motivos": motivos})
        else:
            linhas.append({"id": r.get("id"), "y": y, "x": xs})

    nomes_x = [c["nome"] for c in colunas_x]
    cols = {nm: [l["x"][nm] for l in linhas] for nm in nomes_x}
    constantes = [nm for nm, col in cols.items() if col and len(set(col)) == 1]
    redundantes = []
    for i in range(len(nomes_x)):
        for j in range(i + 1, len(nomes_x)):
            a, b = nomes_x[i], nomes_x[j]
            r_ = E.correlacao(cols[a], cols[b]) if len(linhas) >= 3 else None
            if r_ is not None and abs(r_) >= limiar_redundancia:
                redundantes.append({"a": a, "b": b, "r": r_})
    raras = [c["nome"] for c in colunas_x if c["tipo"] == "indicadora" and c["n_categoria"] < 3]
    espec_hash = json.dumps({"v": variaveis, "ids": sorted(str(l["id"]) for l in linhas)}, sort_keys=True, ensure_ascii=False, default=str)
    dados_hash = json.dumps([[l["id"], l["y"], l["x"]] for l in linhas], sort_keys=True, default=str)
    return {
        "dependente": {"nome": dep["nome"], "transformacao": dep.get("transformacao", "nenhuma")},
        "colunas": [{k: v for k, v in c.items() if k != "var"} for c in colunas_x],
        "linhas": linhas, "n_usados": len(linhas), "n_selecionados": len(base), "excluidos": excluidos,
        "problemas": {"ausentes_por_variavel": ausentes, "constantes": constantes, "redundantes": redundantes,
                      "categorias_com_menos_de_3_dados": raras},
        "assinatura": hashlib.sha256((espec_hash + dados_hash).encode()).hexdigest()[:16],
    }


def _inverte(y: float, t: str) -> float | None:
    if t == "nenhuma": return y
    if t == "ln": return math.exp(y)
    if t == "raiz": return y * y if y >= 0 else None
    if t == "inversa": return 1.0 / y if y != 0 else None
    if t == "quadrado": return math.sqrt(y) if y >= 0 else None
    return None


def ajustar_modelo(registros: list[dict], variaveis: list[dict], ids_usados: list[Any] | None = None,
                   avaliando: dict | None = None, nivel_confianca: float = 0.80) -> dict:
    """Monta a matriz, ajusta o OLS e devolve diagnósticos, suficiência amostral e (se informado) a estimativa do avaliando."""
    mat = montar_matriz(registros, variaveis, ids_usados)
    nomes = [c["nome"] for c in mat["colunas"]]
    if not nomes:
        raise EspecificacaoInvalida("selecione ao menos uma variável independente")
    if mat["problemas"]["constantes"]:
        raise EspecificacaoInvalida(f"variáveis constantes na amostra utilizada: {', '.join(mat['problemas']['constantes'])}")
    y = [l["y"] for l in mat["linhas"]]
    cols = {nm: [l["x"][nm] for l in mat["linhas"]] for nm in nomes}
    suf = E.suficiencia(mat["n_selecionados"], mat["n_usados"], len(nomes), len(mat["excluidos"]))
    try:
        mod = E.regressao(y, cols, nivel_confianca)
    except E.ModeloSingular as e:
        raise EspecificacaoInvalida(f"modelo singular: {e}")
    except ValueError as e:
        raise EspecificacaoInvalida(str(e))
    saida: dict = {"matriz": {k: mat[k] for k in ("dependente", "colunas", "n_usados", "n_selecionados", "excluidos", "problemas", "assinatura")},
                   "suficiencia": suf, "modelo": {k: v for k, v in mod.items() if not k.startswith("_")}}
    ids = [l["id"] for l in mat["linhas"]]
    saida["observacoes"] = [{"id": i, "y": yy, "ajustado": f, "residuo": r, "padronizado": s, "alavancagem": h, "cook": c}
                            for i, yy, f, r, s, h, c in zip(ids, y, mod["ajustados"], mod["residuos"], mod["residuos_padronizados"], mod["alavancagem"], mod["distancia_cook"])]
    n, p = mod["n"], mod["k"] + 1
    saida["observacoes_influentes"] = [o["id"] for o in saida["observacoes"] if o["cook"] > 4.0 / n or o["alavancagem"] > 2.0 * p / n]
    saida["alertas_modelo"] = []
    if any(v > 10 for v in mod["vif"].values()):
        saida["alertas_modelo"].append("VIF acima de 10: indício de multicolinearidade.")
    if mod["normalidade"]["p_valor"] < 0.05:
        saida["alertas_modelo"].append("Jarque–Bera rejeita normalidade dos resíduos a 5% (avaliar o conjunto dos diagnósticos).")
    if mod["heterocedasticidade_bp"] and mod["heterocedasticidade_bp"]["p_valor"] < 0.05:
        saida["alertas_modelo"].append("Breusch–Pagan indica heterocedasticidade a 5%.")
    if mod["F_p_valor"] is not None and mod["F_p_valor"] > 0.05:
        saida["alertas_modelo"].append("Teste F não significativo a 5%: o modelo, em conjunto, não se distingue de uma constante.")
    saida["aviso_metodologico"] = ("Resultados exploratórios/diagnósticos determinísticos. A escolha do modelo, a coerência econômica dos sinais, "
                                   "o atendimento integral à NBR 14653-2 e a responsabilidade técnica são do avaliador.")
    if avaliando is not None:
        faltam = [nm for nm in nomes if nm not in avaliando]
        if faltam:
            raise EspecificacaoInvalida(f"valores do imóvel avaliando ausentes para: {', '.join(faltam)}")
        x0 = {nm: float(avaliando[nm]) for nm in nomes}
        pr = E.predizer(mod, x0, nivel_confianca)
        t = mat["dependente"]["transformacao"]
        conv = {k: (_inverte(v, t) if isinstance(v, float) else [_inverte(a, t) for a in v] if isinstance(v, list) else v) for k, v in pr.items()
                if k in ("estimativa", "ic", "ip")}
        saida["estimativa"] = {"escala_modelo": pr, "escala_original": conv, "transformacao_dependente": t,
                               "extrapolacao": E.extrapolacao(cols, x0),
                               "grau_precisao_ic80": E.grau_precisao(pr["amplitude_ic_relativa"]) if t == "nenhuma" else None,
                               "nota": "Na escala original o valor retransformado de ln/raiz/inversa/quadrado tende à mediana, não à média."}
    return saida


def exploratoria(registros: list[dict], campos_numericos: list[str], campos_categoricos: list[str] | None = None) -> dict:
    """Análise exploratória (NÃO é diagnóstico de modelo). Outliers são apenas sinalizados (critério de Tukey), nunca removidos."""
    campos_categoricos = campos_categoricos or []
    n = len(registros)
    num, qualidade = {}, {}
    cols_completas: dict[str, list[float]] = {}
    for c in campos_numericos:
        vals = [_num(r.get(c)) for r in registros]
        v = [x for x in vals if x is not None]
        d = E.descritiva(v)
        if d["n"] >= 4:
            q1, q3 = d["q1"], d["q3"]
            lim = (q1 - 1.5 * d["iqr"], q3 + 1.5 * d["iqr"])
            d["possiveis_outliers"] = [r.get("id") for r, x in zip(registros, vals) if x is not None and (x < lim[0] or x > lim[1])]
        num[c] = d
        flags = []
        if n and len(v) < n:
            flags.append("valores ausentes")
        if len(set(v)) == 1 and v:
            flags.append("variável constante")
        elif d.get("coef_variacao") is not None and abs(d["coef_variacao"]) < 0.05:
            flags.append("baixa variabilidade (CV < 5%)")
        qualidade[c] = {"completude_pct": round(100 * len(v) / n, 1) if n else 0.0, "ausentes": n - len(v), "alertas": flags}
        if len(v) == n and n:
            cols_completas[c] = v
    corr = E.matriz_correlacao(cols_completas) if len(cols_completas) >= 2 and n >= 3 else {"variaveis": [], "matriz": []}
    altas = []
    nm = corr["variaveis"]
    for i in range(len(nm)):
        for j in range(i + 1, len(nm)):
            r_ = corr["matriz"][i][j]
            if r_ is not None and abs(r_) >= 0.8:
                altas.append({"a": nm[i], "b": nm[j], "r": r_})
    cat = {}
    for c in campos_categoricos:
        cont: dict[str, int] = {}
        for r in registros:
            val = r.get(c)
            key = "(não informado)" if val in (None, "", "NAO_INFORMADO") else str(val)
            cont[key] = cont.get(key, 0) + 1
        topo = max(cont.values()) if cont else 0
        cat[c] = {"contagem": dict(sorted(cont.items(), key=lambda kv: -kv[1])), "categorias": len(cont),
                  "desbalanceada": bool(cont) and topo / n > 0.8, "com_menos_de_3": [k for k, v in cont.items() if v < 3]}
    return {"n": n, "numericas": num, "qualidade": qualidade, "correlacao": corr, "correlacoes_elevadas": altas, "categoricas": cat,
            "nota": "Indicadores exploratórios: não substituem o diagnóstico de um modelo ajustado nem justificam, isoladamente, a escolha de variáveis."}


def registro_de_amostra(a) -> dict:
    """AmostraMercado -> registro plano usado pela base, exploratória e modelagem (valores observados, sem inferências).
    Zero/falso vindo do normalizador significa "não informado/não mencionado no anúncio", nunca "ausente": vira None."""
    d = a.model_dump() if hasattr(a, "model_dump") else dict(a)
    return {
        "id": d["id_amostra"], "fonte": d["fonte"], "data_coleta": d["data_coleta"], "natureza": "oferta",
        "uf": d["uf"], "cidade": d["cidade"], "bairro": d["bairro"], "tipo": d["tipo_imovel"], "finalidade": d["finalidade"],
        "valor_total": d["valor_oferta"], "area_privativa": d["area_m2"], "valor_unitario": d["valor_m2"],
        "quartos": d["quartos"], "suites": d["suites"] or None, "banheiros": d["banheiros"], "vagas": d["vagas"], "andar": d["andar"],
        "condominio": d["condominio_rs"], "iptu": d["iptu_rs"], "elevador": d["elevador"] or None, "piscina": d["piscina"] or None,
        "churrasqueira": d["churrasqueira"] or None, "portaria_24h": d["portaria_24h"] or None,
        "titulo": d["titulo_anuncio"], "descricao": d.get("descricao_anuncio") or "", "url": d["url_anuncio"], "fotos": d["fotos"],
        "alerta": d["alerta_saneamento"], "fora_filtros": d["fora_filtros"], "motivos": d["motivos"], "completude": d["completude"],
    }
