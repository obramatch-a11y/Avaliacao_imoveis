"""Classificação de qualidade e compatibilidade dos anúncios. Nada é apagado: cada amostra recebe
motivos legíveis, e o avaliador decide. Outlier estatístico nunca exclui sozinho."""
import re
from app.models import AmostraMercado, BuscaImovelInput

PRECO_PARCIAL_RE = re.compile(
    r"(entrada\s+(de|a partir)|parcelas?\s+de|presta[cç][aã]o|a partir de\s+r\$|di[aá]ria|temporada|leil[aã]o|r\$\s*[\d.]+\s*(/|por)\s*m[eê]s)",
    re.IGNORECASE,
)


def avaliar(a: AmostraMercado, p: BuscaImovelInput, texto: str = "") -> tuple[bool, list[str], int]:
    """Retorna (fora_dos_filtros, motivos, itens_completos_de_6)."""
    fora: list[str] = []
    aviso: list[str] = []

    v, area = a.valor_oferta, a.area_m2
    if p.preco_min and (v is None or v < p.preco_min):
        fora.append(f"Preço abaixo do mínimo pedido (R$ {p.preco_min:,.0f})".replace(",", "."))
    if p.preco_max and (v is None or v > p.preco_max):
        fora.append(f"Preço acima do máximo pedido (R$ {p.preco_max:,.0f})".replace(",", "."))
    if p.area_min and (area is None or area < p.area_min):
        fora.append(f"Área abaixo do mínimo pedido ({p.area_min:g} m²)")
    if p.area_max and (area is None or area > p.area_max):
        fora.append(f"Área acima do máximo pedido ({p.area_max:g} m²)")
    if p.quartos_min and (a.quartos is None or a.quartos < p.quartos_min):
        fora.append(f"Menos de {p.quartos_min} quarto(s)")

    if v is not None and p.finalidade == "VENDA" and v < 30000:
        aviso.append("Valor baixo demais para venda: pode ser aluguel, parcela ou entrada")
    if v is not None and p.finalidade == "LOCACAO" and v > 40000:
        aviso.append("Valor alto demais para locação: pode ser preço de venda")
    if PRECO_PARCIAL_RE.search(texto):
        aviso.append("O texto cita entrada, parcela, diária, temporada ou leilão: o preço pode não ser o valor integral")
    if a.alerta_saneamento == "POSSIVEL_OUTLIER":
        aviso.append("R$/m² muito fora do usual para a finalidade (conferir; não é exclusão automática)")
    elif a.alerta_saneamento != "OK":
        aviso.append("Valor ou área ausente/inválido")
    if a.bairro == "NAO_INFORMADO":
        aviso.append("Bairro não informado")

    completos = sum(
        [v is not None, area is not None, a.quartos is not None, a.banheiros is not None, a.bairro != "NAO_INFORMADO", bool(a.fotos)]
    )
    return bool(fora), fora + aviso, completos
