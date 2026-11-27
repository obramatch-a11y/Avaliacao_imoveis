import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from app import modelagem as M

REF = json.loads((pathlib.Path(__file__).parent / "fixtures" / "ref_ols_statsmodels.json").read_text())
D = REF["dados"]
BAIRROS = ["Centro", "Boa Viagem", "Casa Forte"]


def registros():
    out = []
    for i in range(len(D["y"])):
        out.append({"id": i + 1, "valor_unitario": D["y"][i], "area_privativa": D["area"][i], "idade": D["idade"][i],
                    "dist": D["dist"][i], "vagas": D["vagas"][i], "bairro": BAIRROS[i % 3]})
    return out


def V(**o):
    base = [
        {"nome": "Valor unitário", "tipo": "continua", "papel": "dependente", "campo": "valor_unitario"},
        {"nome": "area", "tipo": "continua", "papel": "independente", "campo": "area_privativa"},
        {"nome": "idade", "tipo": "discreta", "papel": "independente", "campo": "idade"},
        {"nome": "dist", "tipo": "continua", "papel": "independente", "campo": "dist"},
        {"nome": "vagas", "tipo": "discreta", "papel": "independente", "campo": "vagas"},
    ]
    return base + o.get("extra", [])


def test_ajuste_reproduz_referencia_statsmodels():
    r = M.ajustar_modelo(registros(), V(), avaliando={"area": 120, "idade": 10, "dist": 1.5, "vagas": 2})
    for a, b in zip(r["modelo"]["coeficientes"], REF["coef"]):
        assert a == pytest.approx(b, rel=1e-7)
    assert r["suficiencia"]["k"] == 4 and r["suficiencia"]["minimos"]["III"] == 30 and r["suficiencia"]["grau_quantitativo_maximo"] == "III"
    assert r["estimativa"]["escala_modelo"]["estimativa"] == pytest.approx(REF["pred"]["mean"], rel=1e-7)
    assert r["estimativa"]["extrapolacao"]["area"]["dentro"] is True
    assert "responsabilidade técnica" in r["aviso_metodologico"]


def test_nominal_vira_indicadoras_com_referencia_e_nunca_codigo_arbitrario():
    extra = [{"nome": "bairro", "tipo": "nominal", "papel": "independente", "campo": "bairro", "referencia": "Centro"}]
    m = M.montar_matriz(registros(), V(extra=extra))
    nomes = [c["nome"] for c in m["colunas"]]
    assert "bairro=Boa Viagem" in nomes and "bairro=Casa Forte" in nomes and "bairro=Centro" not in nomes
    with pytest.raises(M.EspecificacaoInvalida):
        M.montar_matriz(registros(), V(extra=[{"nome": "bairro", "tipo": "nominal", "papel": "independente", "campo": "bairro", "codificacao": "ordinal_mapa"}]))
    with pytest.raises(M.EspecificacaoInvalida):
        M.montar_matriz(registros(), V(extra=[{"nome": "bairro", "tipo": "nominal", "papel": "independente", "campo": "bairro", "referencia": "Inexistente"}]))


def test_ordinal_exige_mapa_e_justificativa():
    with pytest.raises(M.EspecificacaoInvalida):
        M.montar_matriz(registros(), V(extra=[{"nome": "padrao", "tipo": "ordinal", "papel": "independente", "campo": "bairro"}]))


def test_ausentes_ficam_fora_com_motivo_e_nada_e_descartado_por_ser_diferente():
    regs = registros()
    regs[0]["area_privativa"] = None
    regs[1]["valor_unitario"] = 10 ** 9  # valor absurdo: NÃO é descartado automaticamente
    m = M.montar_matriz(regs, V())
    assert m["n_usados"] == len(regs) - 1 and m["excluidos"][0]["id"] == 1 and "area ausente" in m["excluidos"][0]["motivos"][0]
    assert any(l["id"] == 2 for l in m["linhas"])


def test_selecao_de_ids_e_assinatura_reprodutivel():
    ids = list(range(1, 31))
    a = M.montar_matriz(registros(), V(), ids)["assinatura"]
    assert a == M.montar_matriz(registros(), V(), ids)["assinatura"]
    assert a != M.montar_matriz(registros(), V(), ids[:-1])["assinatura"]


def test_constantes_redundancias_e_transformacao_log():
    regs = registros()
    for r in regs:
        r["const"] = 5
        r["area2"] = r["area_privativa"] * 2 + 1
    v = V(extra=[{"nome": "k", "tipo": "continua", "papel": "independente", "campo": "const"},
                 {"nome": "a2", "tipo": "continua", "papel": "independente", "campo": "area2"}])
    m = M.montar_matriz(regs, v)
    assert m["problemas"]["constantes"] == ["k"] and any({"area", "a2"} == {x["a"], x["b"]} for x in m["problemas"]["redundantes"])
    with pytest.raises(M.EspecificacaoInvalida):
        M.ajustar_modelo(regs, v)
    vln = V(); vln[0]["transformacao"] = "ln"
    r = M.ajustar_modelo(registros(), vln, avaliando={"area": 120, "idade": 10, "dist": 1.5, "vagas": 2})
    assert r["estimativa"]["escala_original"]["estimativa"] == pytest.approx(__import__("math").exp(r["estimativa"]["escala_modelo"]["estimativa"]))


def test_exploratoria_sinaliza_sem_remover():
    regs = registros(); regs[3]["area_privativa"] = 5000
    e = M.exploratoria(regs, ["area_privativa", "idade"], ["bairro"])
    assert 4 in e["numericas"]["area_privativa"]["possiveis_outliers"] and e["n"] == 40
    assert e["categoricas"]["bairro"]["categorias"] == 3 and "não substituem" in e["nota"]


def test_endpoints_api():
    from app.main import app
    c = TestClient(app)
    corpo = {"registros": registros(), "variaveis": V(), "avaliando": {"area": 100, "idade": 5, "dist": 1, "vagas": 1}}
    r = c.post("/api/modelo", json=corpo)
    assert r.status_code == 200 and r.json()["modelo"]["n"] == 40
    assert c.post("/api/modelo", json={"registros": registros(), "variaveis": []}).status_code == 422
    assert c.post("/api/matriz", json={"registros": registros(), "variaveis": V()}).json()["n_usados"] == 40
    assert c.post("/api/exploratoria", json={"registros": registros(), "numericas": ["idade"]}).status_code == 200
    s = c.get("/api/suficiencia?n_coletados=50&n_utilizaveis=40&k=6").json()
    assert s["minimos"] == {"I": 21, "II": 28, "III": 42}
