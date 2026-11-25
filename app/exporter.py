import csv
import io
from app.models import AmostraSISDEA

COLUNAS_COMPLETAS = [
    "id_amostra",
    "fonte",
    "data_coleta",
    "uf",
    "cidade",
    "bairro",
    "tipo_imovel",
    "finalidade",
    "valor_oferta",
    "area_m2",
    "valor_m2",
    "quartos",
    "suites",
    "banheiros",
    "vagas",
    "andar",
    "condominio_rs",
    "iptu_rs",
    "elevador",
    "piscina",
    "churrasqueira",
    "portaria_24h",
    "alerta_saneamento",
    "url_anuncio",
]

COLUNAS_SISDEA_NUMERICAS = [
    "id_amostra",
    "valor_oferta",
    "area_m2",
    "valor_m2",
    "quartos",
    "suites",
    "banheiros",
    "vagas",
    "andar",
    "condominio_rs",
    "iptu_rs",
    "elevador",
    "piscina",
    "churrasqueira",
    "portaria_24h",
]


def gerar_csv_sisdea(
    amostras: list[AmostraSISDEA],
    apenas_numericas: bool = False,
) -> str:
    colunas = COLUNAS_SISDEA_NUMERICAS if apenas_numericas else COLUNAS_COMPLETAS
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=colunas,
        delimiter=";",
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for idx, amostra in enumerate(amostras, start=1):
        row = amostra.model_dump()
        row["id_amostra"] = idx
        writer.writerow(row)

    return "\ufeff" + buffer.getvalue()
