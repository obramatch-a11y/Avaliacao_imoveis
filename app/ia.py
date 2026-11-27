"""IA da plataforma (opcional): extrai dados explícitos da descrição de um anúncio usando UMA chave do operador (GEMINI_API_KEY).

Regras: exige login; só texto de anúncio (limite de tamanho); limite por pessoa e global (protege a cota gratuita);
nenhuma sugestão é aceita sem trecho de evidência literal no texto; a chave nunca sai do servidor.
"""
import asyncio
import json
import os
import re
import time
import unicodedata

import httpx

CAMPOS = {"quartos": "num", "suites": "num", "banheiros": "num", "vagas": "num", "andar": "num", "idade": "num",
          "area_construida": "num", "area_territorial": "num", "condominio": "num", "iptu": "num",
          "padrao": "txt", "conservacao": "txt", "elevador": "bool", "piscina": "bool", "varanda": "bool", "vista_mar": "bool"}
MAX_TEXTO = 3000
POR_PESSOA_HORA = 20
POR_PESSOA_DIA = 80
GLOBAL_DIA = 1000
_uso: dict[str, list[float]] = {}
_global: list[float] = []


def disponivel() -> bool:
    return bool((os.getenv("GEMINI_API_KEY") or "").strip())


def modelo() -> str:
    m = (os.getenv("GEMINI_MODEL") or "gemini-flash-latest").strip()
    return "gemini-flash-latest" if m == "gemini-2.5-flash" else m


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn").lower())


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    return float(m.group(0).replace(",", ".")) if m else None


def limite_ok(sub: str, agora: float | None = None) -> str | None:
    """Devolve None se pode usar, ou a mensagem do limite atingido (e registra o uso quando pode)."""
    t = agora or time.time()
    u = [x for x in _uso.get(sub, []) if t - x < 86400]
    g = [x for x in _global if t - x < 86400]
    if len(g) >= GLOBAL_DIA:
        _uso[sub], _global[:] = u, g
        return "A cota gratuita diária da plataforma acabou. Tente amanhã ou use a sua própria chave."
    if len(u) >= POR_PESSOA_DIA:
        return "Você atingiu o limite diário de usos da IA."
    if len([x for x in u if t - x < 3600]) >= POR_PESSOA_HORA:
        return "Muitas consultas na última hora. Aguarde um pouco."
    u.append(t)
    g.append(t)
    _uso[sub], _global[:] = u, g
    return None


def montar_prompt(texto: str) -> str:
    return ("Você extrai dados de anúncios imobiliários brasileiros. Use SOMENTE o texto abaixo; não invente nada e não deduza o que não está escrito. "
            'Responda um JSON {"itens":[{"campo":"...","valor":...,"evidencia":"trecho copiado literalmente do texto"}]}. '
            "Campos permitidos: " + ", ".join(CAMPOS) + ". Booleanos só como true quando o texto afirma (nunca false por ausência). "
            'Se não houver dado explícito, devolva {"itens":[]}.\n\nTEXTO:\n' + texto)


def validar_itens(texto: str, itens) -> tuple[list[dict], int]:
    nt, ok, rej = _norm(texto), [], 0
    for it in itens if isinstance(itens, list) else []:
        if not isinstance(it, dict):
            rej += 1
            continue
        campo, ev, val = it.get("campo"), str(it.get("evidencia") or "").strip(), it.get("valor")
        tipo = CAMPOS.get(campo)
        if not tipo or val is None or len(ev) < 3 or _norm(ev) not in nt:
            rej += 1
            continue
        if tipo == "num":
            val = _num(val)
            if val is None or val < 0 or val > 1e9:
                rej += 1
                continue
        elif tipo == "bool":
            if val is not True:
                rej += 1
                continue
            val = 1
        else:
            val = str(val)[:60]
        ok.append({"campo": campo, "valor": val, "evidencia": ev[:200]})
    return ok, rej


async def extrair(texto: str) -> tuple[list[dict], int]:
    chave = (os.getenv("GEMINI_API_KEY") or "").strip()
    corpo = {"contents": [{"parts": [{"text": montar_prompt(texto)}]}], "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    r = None
    # 503 = alta demanda temporária: tenta de novo e, por fim, um modelo mais leve
    for mdl, espera in ((modelo(), 0), (modelo(), 2.5), (modelo(), 2.5), ("gemini-flash-lite-latest", 1)):
        if espera:
            await asyncio.sleep(espera)
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.post(f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent", headers={"x-goog-api-key": chave}, json=corpo)
        if r.status_code != 503:
            break
    if r.status_code == 429:
        raise RuntimeError("cota")
    if r.status_code != 200:
        raise RuntimeError(f"http_{r.status_code}")
    partes = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    bruto = "".join(p.get("text", "") for p in partes).strip()
    bruto = re.sub(r"^```(?:json)?|```$", "", bruto).strip()
    try:
        j = json.loads(bruto)
    except ValueError as e:
        raise RuntimeError("formato") from e
    return validar_itens(texto, j.get("itens"))
