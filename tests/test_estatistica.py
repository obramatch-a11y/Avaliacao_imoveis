"""Validação do motor estatístico contra valores de referência gerados com statsmodels 0.15 (OLS, OLSInfluence,
het_breuschpagan, jarque_bera, get_prediction) sobre um conjunto sintético fixo (tests/fixtures/ref_ols_statsmodels.json)."""
import json
import math
import pathlib

import pytest

from app import estatistica as E

REF = json.loads((pathlib.Path(__file__).parent / "fixtures" / "ref_ols_statsmodels.json").read_text())
D = REF["dados"]
COL = {"area": D["area"], "idade": D["idade"], "dist": D["dist"], "vagas": D["vagas"]}


def prox(a, b, rel=1e-7):
    assert a == pytest.approx(b, rel=rel, abs=1e-9)


@pytest.fixture(scope="module")
def m():
    return E.regressao(D["y"], COL, nivel_confianca=0.80)


def test_coeficientes_erros_t_p_e_ic(m):
    for a, b in zip(m["coeficientes"], REF["coef"]): prox(a, b)
    for a, b in zip(m["erros_padrao"], REF["se"]): prox(a, b)
    for a, b in zip(m["t"], REF["t"]): prox(a, b)
    for a, b in zip(m["p_valores"], REF["p"]): prox(a, b, 1e-6)
    for (lo, hi), (rlo, rhi) in zip(m["intervalos_confianca"], REF["ci80"]):
        prox(lo, rlo); prox(hi, rhi)


def test_ajuste_global(m):
    prox(m["r2"], REF["r2"]); prox(m["r2_ajustado"], REF["r2adj"]); prox(m["F"], REF["F"])
    prox(m["F_p_valor"], REF["Fp"], 1e-5); prox(m["erro_padrao_regressao"], REF["sigma"])


def test_diagnosticos(m):
    for a, b in zip(m["alavancagem"], REF["hat"]): prox(a, b)
    for a, b in zip(m["distancia_cook"], REF["cook"]): prox(a, b, 1e-6)
    for a, b in zip(m["residuos_padronizados"], REF["stud_int"]): prox(a, b, 1e-6)
    for a, b in zip(m["vif"].values(), REF["vif"]): prox(a, b, 1e-6)
    prox(m["durbin_watson"], REF["dw"])
    prox(m["heterocedasticidade_bp"]["estatistica"], REF["bp"][0], 1e-6); prox(m["heterocedasticidade_bp"]["p_valor"], REF["bp"][1], 1e-5)
    prox(m["normalidade"]["jarque_bera"], REF["jb"][0], 1e-6); prox(m["normalidade"]["p_valor"], REF["jb"][1], 1e-6)
    prox(m["normalidade"]["assimetria"], REF["jb"][2], 1e-6); prox(m["normalidade"]["curtose"], REF["jb"][3], 1e-6)


def test_predicao_ic_e_ip(m):
    x = dict(zip(["area", "idade", "dist", "vagas"], REF["pred"]["x"]))
    # a referência foi calculada com [120, 10, 1.5, 2] -> ordem area, idade, dist, vagas
    r = E.predizer(m, x, 0.80)
    prox(r["estimativa"], REF["pred"]["mean"]); prox(r["ic"][0], REF["pred"]["ci"][0]); prox(r["ic"][1], REF["pred"]["ci"][1])
    prox(r["ip"][0], REF["pred"]["ip"][0]); prox(r["ip"][1], REF["pred"]["ip"][1])


def test_descritiva_igual_numpy_e_correlacao():
    np = pytest.importorskip("numpy")
    v = D["area"]
    d = E.descritiva(v)
    prox(d["media"], float(np.mean(v))); prox(d["mediana"], float(np.median(v))); prox(d["desvio_padrao"], float(np.std(v, ddof=1)))
    prox(d["q1"], float(np.percentile(v, 25))); prox(d["q3"], float(np.percentile(v, 75)))
    prox(E.correlacao(D["area"], D["y"]), float(np.corrcoef(D["area"], D["y"])[0, 1]))


def test_distribuicoes_contra_scipy():
    st = pytest.importorskip("scipy.stats")
    for df in (3, 11, 35):
        prox(E.t_ppf(0.9, df), float(st.t.ppf(0.9, df)), 1e-9)
    prox(E.f_sf(4.2, 3, 30), float(st.f.sf(4.2, 3, 30)), 1e-9)
    prox(E.chi2_sf(7.3, 3), float(st.chi2.sf(7.3, 3)), 1e-9)


def test_singular_e_poucos_dados():
    with pytest.raises(E.ModeloSingular):
        E.regressao([1, 2, 3, 4, 5, 7], {"a": [1, 2, 3, 4, 5, 6], "b": [2, 4, 6, 8, 10, 12]})
    with pytest.raises(ValueError):
        E.regressao([1, 2, 3], {"a": [1, 2, 3], "b": [3, 1, 2]})


def test_suficiencia_nbr14653_2_exemplo_do_briefing():
    s = E.suficiencia(60, 40, k=6)
    assert s["minimos"] == {"I": 21, "II": 28, "III": 42} and s["deficit"]["III"] == 2 and s["grau_quantitativo_maximo"] == "II"
    assert E.suficiencia(10, 9, k=3)["alertas"] and E.suficiencia(10, 9, k=3)["grau_quantitativo_maximo"] is None
    assert E.grau_precisao(0.28) == "III" and E.grau_precisao(0.45) == "I" and E.grau_precisao(0.6) is None
