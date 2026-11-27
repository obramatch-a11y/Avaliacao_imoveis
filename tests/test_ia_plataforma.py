import httpx
from fastapi.testclient import TestClient

from app import conta, ia
from app.main import app

c = TestClient(app)
TXT = "Apartamento com 2 suítes, piscina e 3 vagas cobertas. Prédio novo."


def _login(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    c.cookies.set(conta.COOKIE, conta.criar_sessao({"sub": "42", "email": "a@b.com", "nome": "Ana"}))


def test_validacao_rejeita_evidencia_inventada_e_false_por_ausencia():
    itens = [{"campo": "suites", "valor": 2, "evidencia": "2 suítes"}, {"campo": "idade", "valor": 10, "evidencia": "10 anos de construído"},
             {"campo": "piscina", "valor": True, "evidencia": "piscina"}, {"campo": "varanda", "valor": False, "evidencia": "varanda"},
             {"campo": "inexistente", "valor": 1, "evidencia": "2 suítes"}, {"campo": "vagas", "valor": "3 vagas", "evidencia": "3 vagas cobertas"}]
    ok, rej = ia.validar_itens(TXT, itens)
    assert {i["campo"] for i in ok} == {"suites", "piscina", "vagas"} and rej == 3
    assert [i for i in ok if i["campo"] == "vagas"][0]["valor"] == 3.0


def test_endpoint_exige_login_e_chave_do_operador(monkeypatch):
    c.cookies.clear()
    assert c.post("/api/ia/extrair", json={"texto": TXT}).status_code == 401
    _login(monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert c.post("/api/ia/extrair", json={"texto": TXT}).status_code == 503
    assert c.get("/auth/config").json()["ia_servidor"] is False


def test_endpoint_fluxo_limite_e_segredo(monkeypatch):
    _login(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSEGREDO_DO_OPERADOR_123456")
    ia._uso.clear(); ia._global.clear()
    visto = {}

    class R:
        status_code = 200
        def json(self):
            import json
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({"itens": [{"campo": "suites", "valor": 2, "evidencia": "2 suítes"}, {"campo": "idade", "valor": 9, "evidencia": "inventado"}]})}]}}]}

    class Cli:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            visto["h"] = headers
            return R()
    monkeypatch.setattr(httpx, "AsyncClient", Cli)
    j = c.post("/api/ia/extrair", json={"texto": TXT}).json()
    assert j["itens"] == [{"campo": "suites", "valor": 2.0, "evidencia": "2 suítes"}] and j["rejeitados"] == 1
    assert "SEGREDO" not in str(j) and visto["h"]["x-goog-api-key"].startswith("AIza")
    assert c.get("/auth/config").json()["ia_servidor"] is True
    assert c.post("/api/ia/extrair", json={"texto": "curto"}).status_code == 422
    for _ in range(ia.POR_PESSOA_HORA):
        c.post("/api/ia/extrair", json={"texto": TXT})
    assert c.post("/api/ia/extrair", json={"texto": TXT}).status_code == 429


def test_503_tenta_de_novo_e_usa_modelo_leve(monkeypatch):
    import asyncio, json as _j
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaX" * 5)
    chamadas = []

    async def sem_espera(_): return None
    monkeypatch.setattr(asyncio, "sleep", sem_espera)

    class R:
        def __init__(self, s): self.status_code = s
        def json(self): return {"candidates": [{"content": {"parts": [{"text": _j.dumps({"itens": [{"campo": "suites", "valor": 2, "evidencia": "2 suítes"}]})}]}}]}

    class Cli:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            chamadas.append(url)
            return R(200 if "lite" in url else 503)
    monkeypatch.setattr(httpx, "AsyncClient", Cli)
    itens, rej = asyncio.run(ia.extrair(TXT))
    assert itens[0]["campo"] == "suites" and len(chamadas) == 4 and "lite" in chamadas[-1]


def test_descricao_do_anuncio_chega_na_amostra():
    from app.modelagem import registro_de_amostra
    from app.normalizer import normalizar_registro_bruto
    raw = {"titulo": "Apto Piedade", "descricao": "3 quartos, 2 vagas, piscina", "preco": "R$ 400.000", "area": "80", "detalhes": "x"}
    a = normalizar_registro_bruto(1, raw, "PE", "Jaboatão dos Guararapes", "apartamento", "venda")
    assert registro_de_amostra(a)["descricao"] == "3 quartos, 2 vagas, piscina"
    raw["descricao"] = ""
    a2 = normalizar_registro_bruto(2, raw, "PE", "Jaboatão dos Guararapes", "apartamento", "venda")
    assert registro_de_amostra(a2)["descricao"] == ""
