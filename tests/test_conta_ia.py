import asyncio

from fastapi.testclient import TestClient

from app import conta
from app.main import app

c = TestClient(app)


def _logar(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    ck = conta.criar_sessao({"sub": "123", "email": "a@b.com", "nome": "Ana B"})
    c.cookies.set(conta.COOKIE, ck)


def test_ia_exige_login():
    c.cookies.clear()
    assert c.get("/auth/ia").status_code == 401
    assert c.post("/auth/ia", data={"chave": "A" * 30}).status_code == 401


def test_ia_guarda_cifrada_por_usuario_sem_apagar_o_resto(monkeypatch):
    _logar(monkeypatch)
    monkeypatch.setattr(conta, "cofre_disponivel", lambda: True)
    chamadas = []

    async def falso(metodo, sub, corpo=None, params=None):
        chamadas.append((metodo, sub, corpo, params))

        class R:
            status_code = 200
        return R()
    monkeypatch.setattr(conta, "_chamar", falso)
    r = c.post("/auth/ia", data={"chave": "AIza" + "k" * 30, "modelo": "gemini-2.5-flash"})
    assert r.json()["ok"] is True
    metodo, sub, corpo, params = chamadas[0]
    assert sub == "123" and metodo == "PATCH"
    assert "AIza" not in str(corpo)  # nunca em claro
    assert ("updateMask.fieldPaths", "ia_chave_cifrada") in params  # só toca nos próprios campos
    assert c.post("/auth/ia", data={"chave": "curta"}).status_code == 422


def test_ia_leitura_so_da_sessao_do_dono(monkeypatch):
    _logar(monkeypatch)
    monkeypatch.setattr(conta, "cofre_disponivel", lambda: True)
    visto = []

    async def buscar(sub):
        visto.append(sub)
        return {"ia_chave": "AIzaSECRETA" + "x" * 20, "ia_modelo": "m"}
    monkeypatch.setattr(conta, "buscar_extra", buscar)
    j = c.get("/auth/ia").json()
    assert visto == ["123"] and j["chave"].startswith("AIza") and j["modelo"] == "m"
    c.cookies.set(conta.COOKIE, "forjado.assinatura")
    assert c.get("/auth/ia").status_code == 401


def test_chave_scrapingant_nao_sobrescreve_documento(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(conta, "cofre_disponivel", lambda: True)
    vistos = []

    async def falso(metodo, sub, corpo=None, params=None):
        vistos.append(params)

        class R:
            status_code = 200
        return R()
    monkeypatch.setattr(conta, "_chamar", falso)
    assert asyncio.run(conta.guardar_chave("123", "a@b.com", "TOKEN" * 8)) is True
    assert vistos[0] and ("updateMask.fieldPaths", "chave_cifrada") in vistos[0]
