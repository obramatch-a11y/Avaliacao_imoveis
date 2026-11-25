import re
import unicodedata
from datetime import date
from typing import Optional
from app.models import AmostraMercado


def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def limpar_valor_monetario(texto: Optional[str]) -> Optional[float]:
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return round(float(texto), 2) if float(texto) > 0 else None
    limpo = re.sub(r"[^\d,.]", "", str(texto))
    if not limpo:
        return None
    if "," in limpo and "." in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    elif limpo.count(".") >= 1:
        partes = limpo.split(".")
        if len(partes[-1]) == 3:
            limpo = "".join(partes)
    try:
        valor = float(limpo)
        return round(valor, 2) if valor > 0 else None
    except ValueError:
        return None


def limpar_area(texto: Optional[str]) -> Optional[float]:
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return round(float(texto), 2) if float(texto) > 0 else None
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(texto))
    if not match:
        return None
    try:
        area = float(match.group(1).replace(",", "."))
        return round(area, 2) if area > 0 else None
    except ValueError:
        return None


def extrair_inteiro(texto: Optional[str]) -> Optional[int]:
    if texto is None:
        return None
    if isinstance(texto, int):
        return texto
    match = re.search(r"(\d+)", str(texto))
    return int(match.group(1)) if match else None


def detectar_binario(texto_completo: str, palavras_chave: list[str]) -> int:
    base = remover_acentos(texto_completo).lower()
    for termo in palavras_chave:
        if termo in base:
            return 1
    return 0


def extrair_andar(texto_completo: str) -> Optional[int]:
    base = remover_acentos(texto_completo).lower()
    if "terreo" in base:
        return 0
    match = re.search(r"(\d{1,2})\s*(?:o|º|°)?\s*andar", base)
    if match:
        return int(match.group(1))
    return None


def diagnosticar_saneamento(
    valor: Optional[float],
    area: Optional[float],
    finalidade: str,
) -> str:
    if not valor or valor <= 0:
        return "VALOR_AUSENTE"
    if not area or area <= 5:
        return "AREA_AUSENTE_OU_INVALIDA"
    valor_m2 = valor / area
    if finalidade == "VENDA" and (valor < 15000 or valor_m2 < 300 or valor_m2 > 60000):
        return "POSSIVEL_OUTLIER"
    if finalidade == "LOCACAO" and (valor < 200 or valor_m2 < 3 or valor_m2 > 500):
        return "POSSIVEL_OUTLIER"
    return "OK"


def normalizar_registro_bruto(
    idx: int,
    raw: dict,
    uf: str,
    cidade: str,
    tipo_imovel: str,
    finalidade: str,
) -> AmostraMercado:
    titulo = str(raw.get("titulo", "")).strip()
    descricao = str(raw.get("descricao", "")).strip()
    detalhes = str(raw.get("detalhes", "")).strip()
    texto_unificado = f"{titulo} {detalhes} {descricao}"

    valor = limpar_valor_monetario(raw.get("preco"))
    area = limpar_area(raw.get("area"))
    valor_m2 = round(valor / area, 2) if (valor and area and area > 0) else None

    quartos = extrair_inteiro(raw.get("quartos"))
    banheiros = extrair_inteiro(raw.get("banheiros"))
    vagas = extrair_inteiro(raw.get("vagas")) or 0
    suites = extrair_inteiro(raw.get("suites")) or 0

    condominio = limpar_valor_monetario(raw.get("condominio"))
    iptu = limpar_valor_monetario(raw.get("iptu"))
    andar = extrair_andar(texto_unificado)

    elevador = detectar_binario(texto_unificado, ["elevador"])
    piscina = detectar_binario(texto_unificado, ["piscina"])
    churrasqueira = detectar_binario(
        texto_unificado, ["churrasqueira", "espaco gourmet", "area gourmet"]
    )
    portaria_24h = detectar_binario(
        texto_unificado, ["portaria 24", "condominio fechado", "seguranca 24"]
    )

    bairro_limpo = str(raw.get("bairro", "")).strip() or "NAO_INFORMADO"
    alerta = diagnosticar_saneamento(valor, area, finalidade)

    return AmostraMercado(
        id_amostra=idx,
        fonte=str(raw.get("fonte", "OLX")),
        data_coleta=date.today().isoformat(),
        uf=uf.upper(),
        cidade=cidade.strip(),
        bairro=bairro_limpo,
        tipo_imovel=tipo_imovel,
        finalidade=finalidade,
        valor_oferta=valor,
        area_m2=area,
        valor_m2=valor_m2,
        quartos=quartos,
        suites=suites,
        banheiros=banheiros,
        vagas=vagas,
        andar=andar,
        condominio_rs=condominio,
        iptu_rs=iptu,
        elevador=elevador,
        piscina=piscina,
        churrasqueira=churrasqueira,
        portaria_24h=portaria_24h,
        alerta_saneamento=alerta,
        titulo_anuncio=titulo[:140],
        url_anuncio=str(raw.get("url", "")),
    )
