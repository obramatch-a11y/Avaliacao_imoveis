import io
import zipfile

from fastapi.testclient import TestClient

from app.main import app
from app.xlsx_min import gerar_xlsx

c = TestClient(app)


def test_estacao_base_serve_shell_e_estaticos():
    r = c.get("/base")
    assert r.status_code == 200 and "base-core.js" in r.text and 'id="view"' in r.text
    for f in ("base.css", "base-core.js", "base-grid.js", "base-modules.js"):
        assert c.get(f"/static/{f}").status_code == 200


def test_coleta_inexistente_redireciona():
    assert c.get("/coleta/naoexiste/resultado", follow_redirects=False).status_code == 303


def test_xlsx_valido_e_escapado():
    dados = gerar_xlsx([{"nome": "A/B*?", "cabecalho": ["x", "y"], "linhas": [["<&>", 1.5], [None, True]]}])
    z = zipfile.ZipFile(io.BytesIO(dados))
    assert z.testzip() is None and "xl/worksheets/sheet1.xml" in z.namelist()
    assert "&lt;&amp;&gt;" in z.read("xl/worksheets/sheet1.xml").decode()
    r = c.post("/api/exportar/xlsx", json={"abas": [{"nome": "T", "cabecalho": ["a"], "linhas": [[1]]}]})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert c.post("/api/exportar/xlsx", json={"abas": []}).status_code == 422
