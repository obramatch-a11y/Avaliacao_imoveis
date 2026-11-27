import json

import httpx
from fastapi.testclient import TestClient

from app import conta, ia
from app.main import app

c = TestClient(app)


def _login(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSEGREDO_OPERADOR_123456")
    c.cookies.set(conta.COOKIE, conta.criar_sessao({"sub": "77", "email": "a@b.com", "nome": "Ana"}))
    ia._uso.clear(); ia._global.clear()


def test_ssrf_bloqueia_hosts_privados():
    for h in ("localhost", "127.0.0.1", "169.254.169.254", "10.0.0.5"):
        assert ia.host_publico(h) is False


def test_validar_itens_fotos():
    itens = [{"campo": "conservacao", "valor": "Bom", "evidencia": "pintura nova nas paredes", "confianca": "alta"},
             {"campo": "conservacao", "valor": "excelente", "evidencia": "tudo novo"},
             {"campo": "piscina", "valor": False, "evidencia": "não há piscina visível"},
             {"campo": "piscina", "valor": True, "evidencia": "piscina na varanda"},
             {"campo": "preco", "valor": 1, "evidencia": "qualquer coisa"},
             {"campo": "padrao", "valor": "alto", "evidencia": "x"}]
    ok = ia.validar_itens_fotos(itens)
    assert [(i["campo"], i["valor"]) for i in ok] == [("conservacao", "bom"), ("piscina", 1)]


def test_numeros_fora_detecta_invencao():
    dados = {"r2": 0.3123, "n": 53, "coef": [{"variavel": "area", "coef": 5400.5}]}
    assert ia.numeros_fora("O R² é 0,3123 e há 53 amostras; a área pesa 5400,5.", dados) == []
    assert ia.numeros_fora("O R² explica 31% da variação.", dados) == []
    assert "77,9" in ia.numeros_fora("O erro foi de 77,9 reais.", dados)


def _falso_gemini(monkeypatch, resposta_texto):
    class R:
        status_code = 200
        def json(self): return {"candidates": [{"content": {"parts": [{"text": resposta_texto}]}}]}

    class Cli:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None): return R()
    monkeypatch.setattr(httpx, "AsyncClient", Cli)


def test_rota_texto_exige_login_e_avisa_numeros(monkeypatch):
    c.cookies.clear()
    assert c.post("/api/ia/texto", json={"tipo": "explicar", "dados": {"r2": 0.3}}).status_code == 401
    _login(monkeypatch)
    assert c.post("/api/ia/texto", json={"tipo": "xx", "dados": {}}).status_code == 422
    assert c.post("/api/ia/texto", json={"tipo": "explicar", "dados": {"x": "a" * 9000}}).status_code == 422
    _falso_gemini(monkeypatch, "O R² é 0,3 e o erro foi 999,5.")
    j = c.post("/api/ia/texto", json={"tipo": "explicar", "dados": {"r2": 0.3}}).json()
    assert "999,5" in j["numeros_fora"] and "SEGREDO" not in json.dumps(j)


def test_rota_fotos(monkeypatch):
    c.cookies.clear()
    assert c.post("/api/ia/fotos", json={"fotos": []}).status_code == 422
    assert c.post("/api/ia/fotos", json={"fotos": ["https://x.com/a.jpg"]}).status_code == 401
    _login(monkeypatch)

    async def foto(url): return ("image/jpeg", b"x" * 800)
    monkeypatch.setattr(ia, "buscar_foto", foto)
    _falso_gemini(monkeypatch, json.dumps({"itens": [{"campo": "conservacao", "valor": "regular", "evidencia": "mancha de umidade no teto", "confianca": "media"}], "observacoes": "fotos escuras"}))
    j = c.post("/api/ia/fotos", json={"fotos": ["https://x.com/a.jpg", "http://inseguro.com/b.jpg"]}).json()
    assert j["fotos_lidas"] == 1 and j["itens"][0]["valor"] == "regular"

    async def nada(url): return None
    monkeypatch.setattr(ia, "buscar_foto", nada)
    assert c.post("/api/ia/fotos", json={"fotos": ["https://x.com/a.jpg"]}).status_code == 422
