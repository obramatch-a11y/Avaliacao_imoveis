from typing import Literal, Optional
from pydantic import BaseModel, Field


class BuscaImovelInput(BaseModel):
    uf: str = Field(..., min_length=2, max_length=2, description="Sigla UF (ex: PE, SP, AL)")
    cidade: str = Field(..., min_length=2, description="Nome da cidade")
    bairro: Optional[str] = Field(default="", description="Bairro alvo (opcional)")
    finalidade: Literal["VENDA", "LOCACAO"] = "VENDA"
    tipo_imovel: Literal["APARTAMENTO", "CASA", "TERRENO", "COMERCIAL"] = "APARTAMENTO"
    area_min: Optional[float] = Field(default=None, ge=0)
    area_max: Optional[float] = Field(default=None, ge=0)
    quartos_min: Optional[int] = Field(default=None, ge=0)
    preco_min: Optional[float] = Field(default=None, ge=0)
    preco_max: Optional[float] = Field(default=None, ge=0)
    limite_paginas: int = Field(default=2, ge=1, le=20)


class AmostraMercado(BaseModel):
    id_amostra: int
    fonte: str
    data_coleta: str
    uf: str
    cidade: str
    bairro: str
    tipo_imovel: str
    finalidade: str
    valor_oferta: Optional[float] = None
    area_m2: Optional[float] = None
    valor_m2: Optional[float] = None
    quartos: Optional[int] = None
    suites: int = 0
    banheiros: Optional[int] = None
    vagas: int = 0
    andar: Optional[int] = None
    condominio_rs: Optional[float] = None
    iptu_rs: Optional[float] = None
    elevador: int = 0
    piscina: int = 0
    churrasqueira: int = 0
    portaria_24h: int = 0
    alerta_saneamento: str = "OK"
    titulo_anuncio: str = ""
    descricao_anuncio: str = ""
    url_anuncio: str = ""
    fotos: list[str] = Field(default_factory=list)
    fora_filtros: bool = False
    motivos: list[str] = Field(default_factory=list)
    completude: int = 0
