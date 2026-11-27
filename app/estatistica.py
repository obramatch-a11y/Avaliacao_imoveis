"""Motor estatístico determinístico (Python puro, sem dependências novas) para o método comparativo direto.

Funções: estatística descritiva, correlação, regressão linear múltipla (OLS) com diagnósticos, predição com
intervalos de confiança/predição e assistente de suficiência amostral (NBR 14653-2:2011, tabela de regressão linear).
Os resultados são validados contra statsmodels em tests/test_estatistica.py (valores de referência fixos).
Este módulo NÃO escolhe modelo nem elimina outliers: apenas calcula e diagnostica.
"""
from __future__ import annotations

import math
from typing import Sequence

# ---------------------------------------------------------------------------------------------
# Funções especiais (distribuições)
# ---------------------------------------------------------------------------------------------


def _betacf(a: float, b: float, x: float) -> float:
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        dl = d * c
        h *= dl
        if abs(dl - 1.0) < 1e-15:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Função beta incompleta regularizada I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_bt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    bt = math.exp(ln_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def gammainc_lower(a: float, x: float) -> float:
    """Gama incompleta regularizada P(a, x)."""
    if x <= 0:
        return 0.0
    if x < a + 1.0:
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(1000):
            ap += 1.0
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-16:
                break
        return s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    tiny = 1e-300
    b, c, d = x + 1.0 - a, 1.0 / tiny, 1.0 / (x + 1.0 - a)
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = d if abs(d) > tiny else tiny
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        d = 1.0 / d
        dl = d * c
        h *= dl
        if abs(dl - 1.0) < 1e-15:
            break
    return 1.0 - math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf(x: float, df: float) -> float:
    return max(0.0, min(1.0, 1.0 - gammainc_lower(df / 2.0, x / 2.0))) if x > 0 else 1.0


def t_cdf(t: float, df: float) -> float:
    x = df / (df + t * t)
    p = 0.5 * betainc(df / 2.0, 0.5, x)
    return 1.0 - p if t > 0 else p


def t_sf2(t: float, df: float) -> float:
    """Valor-p bilateral."""
    return betainc(df / 2.0, 0.5, df / (df + t * t))


def f_sf(f: float, d1: float, d2: float) -> float:
    if f <= 0:
        return 1.0
    return betainc(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * f))


def t_ppf(p: float, df: float) -> float:
    """Quantil da t de Student (bisseção; precisão ~1e-12)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p deve estar entre 0 e 1")
    lo, hi = -1e3, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def norm_cdf(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


# ---------------------------------------------------------------------------------------------
# Estatística descritiva
# ---------------------------------------------------------------------------------------------


def percentil(valores: Sequence[float], q: float) -> float:
    """Percentil por interpolação linear (igual ao numpy.percentile padrão). q em [0, 100]."""
    v = sorted(valores)
    if not v:
        raise ValueError("amostra vazia")
    pos = (len(v) - 1) * q / 100.0
    i = int(math.floor(pos))
    j = min(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * (pos - i)


def descritiva(valores: Sequence[float | None]) -> dict:
    v = [float(x) for x in valores if x is not None and not (isinstance(x, float) and math.isnan(x))]
    n = len(v)
    if n == 0:
        return {"n": 0}
    media = sum(v) / n
    var = sum((x - media) ** 2 for x in v) / (n - 1) if n > 1 else None
    dp = math.sqrt(var) if var is not None else None
    cont: dict[float, int] = {}
    for x in v:
        cont[x] = cont.get(x, 0) + 1
    topo = max(cont.values())
    moda = sorted(k for k, c in cont.items() if c == topo) if topo > 1 else []
    q1, q3 = percentil(v, 25), percentil(v, 75)
    return {
        "n": n, "media": media, "mediana": percentil(v, 50), "moda": moda, "minimo": min(v), "maximo": max(v),
        "amplitude": max(v) - min(v), "variancia": var, "desvio_padrao": dp,
        "coef_variacao": (dp / media) if dp is not None and media else None,
        "q1": q1, "q3": q3, "iqr": q3 - q1,
        "percentis": {str(p): percentil(v, p) for p in (5, 10, 25, 50, 75, 90, 95)},
    }


def correlacao(a: Sequence[float], b: Sequence[float]) -> float | None:
    n = len(a)
    if n < 3 or n != len(b):
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sa = sum((x - ma) ** 2 for x in a)
    sb = sum((y - mb) ** 2 for y in b)
    if sa == 0 or sb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sa * sb)


def matriz_correlacao(colunas: dict[str, Sequence[float]]) -> dict:
    nomes = list(colunas)
    return {"variaveis": nomes, "matriz": [[(1.0 if i == j else correlacao(colunas[a], colunas[b])) for j, b in enumerate(nomes)] for i, a in enumerate(nomes)]}


# ---------------------------------------------------------------------------------------------
# Álgebra linear mínima
# ---------------------------------------------------------------------------------------------


class ModeloSingular(ValueError):
    """Matriz X'X singular: variáveis constantes ou perfeitamente colineares."""


def _inversa(m: list[list[float]]) -> list[list[float]]:
    n = len(m)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12 * max(1.0, max(abs(x) for x in a[piv][:n])):
            raise ModeloSingular("variáveis perfeitamente colineares ou constantes")
        a[col], a[piv] = a[piv], a[col]
        p = a[col][col]
        a[col] = [x / p for x in a[col]]
        for r in range(n):
            if r != col and a[r][col] != 0.0:
                f = a[r][col]
                a[r] = [x - f * y for x, y in zip(a[r], a[col])]
    return [row[n:] for row in a]


def _xtx(X: list[list[float]]) -> list[list[float]]:
    p = len(X[0])
    out = [[0.0] * p for _ in range(p)]
    for row in X:
        for i in range(p):
            ri = row[i]
            for j in range(i, p):
                out[i][j] += ri * row[j]
    for i in range(p):
        for j in range(i):
            out[i][j] = out[j][i]
    return out


# ---------------------------------------------------------------------------------------------
# Regressão linear múltipla
# ---------------------------------------------------------------------------------------------


def regressao(y: Sequence[float], colunas: dict[str, Sequence[float]], nivel_confianca: float = 0.80) -> dict:
    """Mínimos quadrados ordinários com intercepto. `colunas`: nome -> valores (já codificados/transformados)."""
    nomes = list(colunas)
    k = len(nomes)
    n = len(y)
    if any(len(c) != n for c in colunas.values()):
        raise ValueError("colunas com tamanhos diferentes")
    p = k + 1
    if n <= p:
        raise ValueError(f"dados insuficientes: n={n} deve ser maior que k+1={p}")
    X = [[1.0] + [float(colunas[nm][i]) for nm in nomes] for i in range(n)]
    Y = [float(v) for v in y]
    XtX_inv = _inversa(_xtx(X))
    Xty = [sum(X[r][c] * Y[r] for r in range(n)) for c in range(p)]
    beta = [sum(XtX_inv[i][j] * Xty[j] for j in range(p)) for i in range(p)]
    fit = [sum(X[r][c] * beta[c] for c in range(p)) for r in range(n)]
    res = [Y[r] - fit[r] for r in range(n)]
    gl = n - p
    sqres = sum(e * e for e in res)
    media_y = sum(Y) / n
    sqt = sum((v - media_y) ** 2 for v in Y)
    sqreg = sqt - sqres
    s2 = sqres / gl
    sigma = math.sqrt(s2)
    r2 = 1.0 - sqres / sqt if sqt > 0 else float("nan")
    r2aj = 1.0 - (n - 1) / gl * (1.0 - r2) if sqt > 0 else float("nan")
    se = [math.sqrt(max(s2 * XtX_inv[i][i], 0.0)) for i in range(p)]
    tvals = [(beta[i] / se[i]) if se[i] > 0 else float("inf") for i in range(p)]
    pvals = [t_sf2(t, gl) for t in tvals]
    tcrit = t_ppf(1.0 - (1.0 - nivel_confianca) / 2.0, gl)
    F = (sqreg / k) / s2 if k > 0 and s2 > 0 else float("nan")
    hat = [sum(X[r][i] * sum(XtX_inv[i][j] * X[r][j] for j in range(p)) for i in range(p)) for r in range(n)]
    stud = [res[r] / (sigma * math.sqrt(max(1.0 - hat[r], 1e-12))) for r in range(n)]
    cook = [(stud[r] ** 2 / p) * (hat[r] / max(1.0 - hat[r], 1e-12)) for r in range(n)]
    dw_den = sum(e * e for e in res)
    dw = sum((res[i] - res[i - 1]) ** 2 for i in range(1, n)) / dw_den if dw_den > 0 else None

    # Normalidade dos resíduos: Jarque–Bera
    m2 = sum(e * e for e in res) / n
    m3 = sum(e ** 3 for e in res) / n
    m4 = sum(e ** 4 for e in res) / n
    assim = m3 / m2 ** 1.5 if m2 > 0 else 0.0
    curt = m4 / m2 ** 2 if m2 > 0 else 3.0
    jb = n / 6.0 * (assim ** 2 + (curt - 3.0) ** 2 / 4.0)
    dentro_1dp = sum(1 for e in stud if abs(e) <= 1.0) / n  # referência normal: ~68%
    dentro_165 = sum(1 for e in stud if abs(e) <= 1.64) / n  # ~90%
    dentro_196 = sum(1 for e in stud if abs(e) <= 1.96) / n  # ~95%

    # Homoscedasticidade: Breusch–Pagan (Koenker, como statsmodels.het_breuschpagan padrão)
    bp = None
    if k >= 1:
        e2 = [e * e for e in res]
        try:
            g = regressao_simples_r2(e2, X)
            lm = n * g
            bp = {"estatistica": lm, "gl": k, "p_valor": chi2_sf(lm, k)}
        except ModeloSingular:
            bp = None

    # VIF
    vif = {}
    if k >= 2:
        for i, nm in enumerate(nomes):
            outras = {o: colunas[o] for o in nomes if o != nm}
            try:
                r2i = regressao(list(colunas[nm]), outras, nivel_confianca)["r2"]
                vif[nm] = 1.0 / (1.0 - r2i) if r2i < 1.0 else float("inf")
            except (ModeloSingular, ValueError):
                vif[nm] = float("inf")

    return {
        "n": n, "k": k, "gl_residuos": gl, "nomes": ["(Intercepto)"] + nomes, "coeficientes": beta, "erros_padrao": se,
        "t": tvals, "p_valores": pvals,
        "intervalos_confianca": [[b - tcrit * s, b + tcrit * s] for b, s in zip(beta, se)], "nivel_confianca": nivel_confianca,
        "r2": r2, "r2_ajustado": r2aj, "r": math.sqrt(r2) if r2 >= 0 else float("nan"),
        "erro_padrao_regressao": sigma, "F": F, "F_p_valor": f_sf(F, k, gl) if k > 0 and F == F else None,
        "sq_regressao": sqreg, "sq_residuos": sqres, "sq_total": sqt,
        "ajustados": fit, "residuos": res, "residuos_padronizados": stud, "alavancagem": hat, "distancia_cook": cook,
        "durbin_watson": dw,
        "normalidade": {"jarque_bera": jb, "p_valor": chi2_sf(jb, 2), "assimetria": assim, "curtose": curt,
                        "pct_dentro_1dp": dentro_1dp, "pct_dentro_1_64dp": dentro_165, "pct_dentro_1_96dp": dentro_196},
        "heterocedasticidade_bp": bp, "vif": vif,
        "_XtX_inv": XtX_inv,
    }


def regressao_simples_r2(y: list[float], X: list[list[float]]) -> float:
    """R² da regressão de y sobre X (X já com intercepto)."""
    n, p = len(y), len(X[0])
    inv = _inversa(_xtx(X))
    xty = [sum(X[r][c] * y[r] for r in range(n)) for c in range(p)]
    b = [sum(inv[i][j] * xty[j] for j in range(p)) for i in range(p)]
    fit = [sum(X[r][c] * b[c] for c in range(p)) for r in range(n)]
    my = sum(y) / n
    sqt = sum((v - my) ** 2 for v in y)
    sqres = sum((y[r] - fit[r]) ** 2 for r in range(n))
    return 1.0 - sqres / sqt if sqt > 0 else 0.0


def predizer(modelo: dict, x0: dict[str, float], nivel_confianca: float | None = None) -> dict:
    """Estimativa pontual, IC da média e IP para um imóvel com valores `x0` (mesmas colunas do modelo)."""
    nomes = modelo["nomes"][1:]
    if set(x0) != set(nomes):
        raise ValueError(f"informe exatamente as variáveis do modelo: {nomes}")
    v = [1.0] + [float(x0[nm]) for nm in nomes]
    inv = modelo["_XtX_inv"]
    p = len(v)
    h0 = sum(v[i] * sum(inv[i][j] * v[j] for j in range(p)) for i in range(p))
    pontual = sum(b * x for b, x in zip(modelo["coeficientes"], v))
    sigma = modelo["erro_padrao_regressao"]
    nc = nivel_confianca or modelo["nivel_confianca"]
    tcrit = t_ppf(1.0 - (1.0 - nc) / 2.0, modelo["gl_residuos"])
    me_ic, me_ip = tcrit * sigma * math.sqrt(h0), tcrit * sigma * math.sqrt(1.0 + h0)
    return {"estimativa": pontual, "alavancagem": h0, "nivel_confianca": nc,
            "ic": [pontual - me_ic, pontual + me_ic], "ip": [pontual - me_ip, pontual + me_ip],
            "amplitude_ic_relativa": (2 * me_ic / pontual) if pontual else None,
            "amplitude_ip_relativa": (2 * me_ip / pontual) if pontual else None}


def extrapolacao(colunas: dict[str, Sequence[float]], x0: dict[str, float]) -> dict[str, dict]:
    """Verifica se o imóvel avaliando está dentro do intervalo amostral de cada variável."""
    out = {}
    for nm, col in colunas.items():
        lo, hi = min(col), max(col)
        out[nm] = {"minimo": lo, "maximo": hi, "valor": x0.get(nm), "dentro": (lo <= x0[nm] <= hi) if nm in x0 else None}
    return out


# ---------------------------------------------------------------------------------------------
# Suficiência amostral — NBR 14653-2:2011 (modelos de regressão linear)
# ---------------------------------------------------------------------------------------------

# Item 1 da tabela de fundamentação para regressão: número mínimo de dados de mercado efetivamente utilizados.
MULTIPLICADOR_GRAU = {"I": 3, "II": 4, "III": 6}
# Item de precisão: amplitude do IC de 80% em torno do valor central.
AMPLITUDE_MAX_PRECISAO = {"III": 0.30, "II": 0.40, "I": 0.50}


def suficiencia(n_coletados: int, n_utilizaveis: int, k: int, n_ausentes: int = 0) -> dict:
    """Quantidade mínima por grau em função de k (variáveis independentes). Atender ao mínimo é condição
    necessária, não suficiente, para o grau de fundamentação."""
    if k < 0:
        raise ValueError("k não pode ser negativo")
    minimos = {g: m * (k + 1) for g, m in MULTIPLICADOR_GRAU.items()}
    deficit = {g: max(0, minimos[g] - n_utilizaveis) for g in minimos}
    grau = next((g for g in ("III", "II", "I") if n_utilizaveis >= minimos[g]), None)
    alertas = []
    if n_utilizaveis < minimos["I"]:
        alertas.append(f"Micronumerosidade: {n_utilizaveis} dado(s) para k={k} (mínimo de 3·(k+1) = {minimos['I']}).")
    if n_utilizaveis <= k + 1:
        alertas.append("Não há graus de liberdade para estimar o modelo.")
    if n_ausentes:
        alertas.append(f"{n_ausentes} dado(s) com informação ausente reduzem a amostra efetivamente utilizável.")
    return {"coletados": n_coletados, "utilizaveis": n_utilizaveis, "k": k, "minimos": minimos, "deficit": deficit,
            "grau_quantitativo_maximo": grau, "alertas": alertas,
            "aviso": "A quantidade mínima, isoladamente, não determina o grau de fundamentação; os demais itens da norma "
                     "(variáveis, extrapolação, significância, etc.) também precisam ser atendidos."}


def grau_precisao(amplitude_ic80_relativa: float | None) -> str | None:
    if amplitude_ic80_relativa is None:
        return None
    for g in ("III", "II", "I"):
        if amplitude_ic80_relativa <= AMPLITUDE_MAX_PRECISAO[g]:
            return g
    return None
