from app.exporter import gerar_csv
from app.normalizer import normalizar_registro_bruto


def test_normalizacao_e_csv():
    raw = {
        "fonte": "OLX",
        "titulo": "Apto 3 quartos com elevador e piscina no 8º andar",
        "preco": "R$ 650.000",
        "area": "92,5 m²",
        "quartos": "3 quartos",
        "vagas": "2 vagas",
        "bairro": "Pajuçara",
        "url": "https://exemplo.com/imovel-1",
    }
    amostra = normalizar_registro_bruto(
        idx=1,
        raw=raw,
        uf="AL",
        cidade="Maceió",
        tipo_imovel="APARTAMENTO",
        finalidade="VENDA",
    )
    assert amostra.valor_oferta == 650000.0
    assert amostra.area_m2 == 92.5
    assert amostra.valor_m2 == round(650000.0 / 92.5, 2)
    assert amostra.elevador == 1
    assert amostra.piscina == 1
    assert amostra.andar == 8
    assert amostra.alerta_saneamento == "OK"

    csv_num = gerar_csv([amostra], apenas_numericas=True)
    assert "valor_oferta;area_m2;valor_m2" in csv_num
    assert "650000.0;92.5;" in csv_num
