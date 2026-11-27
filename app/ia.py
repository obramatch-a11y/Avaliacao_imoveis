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


async def _gemini(partes: list[dict], json_mode: bool = True) -> str:
    """Chamada comum ao Gemini com chave do operador. 503 = alta demanda: tenta de novo e cai para o modelo leve."""
    chave = (os.getenv("GEMINI_API_KEY") or "").strip()
    cfg = {"temperature": 0}
    if json_mode:
        cfg["responseMimeType"] = "application/json"
    corpo = {"contents": [{"parts": partes}], "generationConfig": cfg}
    r = None
    for mdl, espera in ((modelo(), 0), (modelo(), 2.5), (modelo(), 2.5), ("gemini-flash-lite-latest", 1)):
        if espera:
            await asyncio.sleep(espera)
        async with httpx.AsyncClient(timeout=45.0) as cli:
            r = await cli.post(f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent", headers={"x-goog-api-key": chave}, json=corpo)
        if r.status_code != 503:
            break
    if r.status_code == 429:
        raise RuntimeError("cota")
    if r.status_code != 200:
        raise RuntimeError(f"http_{r.status_code}")
    ps = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in ps).strip()


def _json(bruto: str) -> dict:
    bruto = re.sub(r"^```(?:json)?|```$", "", bruto.strip()).strip()
    try:
        j = json.loads(bruto)
    except ValueError as e:
        raise RuntimeError("formato") from e
    return j if isinstance(j, dict) else {}


async def extrair(texto: str) -> tuple[list[dict], int]:
    j = _json(await _gemini([{"text": montar_prompt(texto)}]))
    return validar_itens(texto, j.get("itens"))


# ---------------------------------------------------------------- fotos
FOTO_MAX_BYTES = 1_500_000
FOTO_TIPOS = {"image/jpeg", "image/png", "image/webp"}
CAMPOS_FOTO = {"conservacao": {"ótimo", "bom", "regular", "ruim"}, "padrao": {"alto", "normal", "baixo"}, "piscina": True, "varanda": True}


def host_publico(host: str) -> bool:
    """Proteção SSRF: só hosts que resolvem apenas para endereços públicos."""
    import ipaddress
    import socket
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    if not infos:
        return False
    for i in infos:
        ip = ipaddress.ip_address(i[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
    return True


async def buscar_foto(url: str) -> tuple[str, bytes] | None:
    from urllib.parse import urljoin, urlparse
    atual = url
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as cli:
        for _ in range(3):
            u = urlparse(atual)
            if u.scheme != "https" or not u.hostname or not host_publico(u.hostname):
                return None
            r = await cli.get(atual, headers={"Accept": "image/*", "User-Agent": "InferenciaEstatistica/1.0"})
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                atual = urljoin(atual, r.headers["location"])
                continue
            tipo = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
            if r.status_code != 200 or tipo not in FOTO_TIPOS or len(r.content) > FOTO_MAX_BYTES or len(r.content) < 500:
                return None
            return tipo, r.content
    return None


def montar_prompt_fotos() -> str:
    return ("Você ajuda um engenheiro avaliador a descrever imóveis a partir de FOTOS de anúncios. Descreva só o que é VISÍVEL; não adivinhe. "
            'Responda JSON {"itens":[{"campo":"conservacao|padrao|piscina|varanda","valor":"...","evidencia":"o que se vê, até 120 caracteres","confianca":"baixa|media|alta"}],"observacoes":"até 200 caracteres"}. '
            "conservacao: ótimo, bom, regular ou ruim (estado aparente de pintura, pisos, infiltração, esquadrias). padrao (acabamento): alto, normal ou baixo. "
            "piscina e varanda: valor true somente se aparecem nas fotos. Se as fotos não permitem concluir, omita o campo.")


def validar_itens_fotos(itens) -> list[dict]:
    out = []
    for it in itens if isinstance(itens, list) else []:
        if not isinstance(it, dict):
            continue
        campo, val, ev = it.get("campo"), it.get("valor"), str(it.get("evidencia") or "").strip()
        regra = CAMPOS_FOTO.get(campo)
        if regra is None or len(ev) < 5:
            continue
        if regra is True:
            if val is not True:
                continue
            val = 1
        else:
            val = str(val).strip().lower()
            if val == "otimo":
                val = "ótimo"
            if val not in regra:
                continue
        conf = it.get("confianca") if it.get("confianca") in ("baixa", "media", "alta") else "baixa"
        out.append({"campo": campo, "valor": val, "evidencia": ev[:160], "confianca": conf})
    return out


async def analisar_fotos(urls: list[str]) -> tuple[list[dict], str, int]:
    import base64
    partes, lidas = [{"text": montar_prompt_fotos()}], 0
    for u in urls[:3]:
        f = await buscar_foto(u)
        if f:
            partes.append({"inline_data": {"mime_type": f[0], "data": base64.b64encode(f[1]).decode()}})
            lidas += 1
    if not lidas:
        return [], "", 0
    j = _json(await _gemini(partes))
    return validar_itens_fotos(j.get("itens")), str(j.get("observacoes") or "")[:300], lidas


# ---------------------------------------------------------------- texto (explicação / laudo)
MAX_DADOS = 8000


def _numeros(txt: str) -> list[float]:
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", str(txt)) if x.replace(",", ".").replace(".", "", 1).isdigit()]


def numeros_fora(texto: str, dados) -> list[str]:
    """Números do texto gerado que NÃO aparecem nos dados enviados (aviso de possível invenção)."""
    base = _numeros(json.dumps(dados, ensure_ascii=False))
    fora = []
    for m in re.findall(r"\d+(?:[.,]\d+)?", texto):
        v = float(m.replace(",", ".")) if m.replace(",", ".").replace(".", "", 1).isdigit() else None
        if v is None or (v == int(v) and v <= 12) or 1900 <= v <= 2100 and v == int(v):
            continue
        d = len(m.replace(",", ".").split(".")[1]) if re.search(r"[.,]\d", m) else 0
        if not any(round(x, d) == round(v, d) or round(x * 100, d) == round(v, d) or round(x * 100, 0) == round(v, 0) and d == 0 for x in base):
            fora.append(m)
    return sorted(set(fora))[:12]


def montar_prompt_texto(tipo: str, dados) -> str:
    base = ("Você auxilia um engenheiro avaliador (NBR 14653, Método Comparativo Direto) escrevendo em português do Brasil. Use SOMENTE os números e fatos do JSON abaixo; "
            "NÃO invente números, normas, limites ou conclusões. Não escolha nem aprove o modelo: o julgamento é do engenheiro. Seja claro e curto.\n\n")
    if tipo == "explicar":
        tarefa = ("Explique o resultado desta regressão para um leigo, em até 8 frases curtas: o que o R² significa aqui, quais variáveis parecem pesar mais (pelos coeficientes e p-valores), "
                  "o que os testes de normalidade e heterocedasticidade indicam e o que PROVAVELMENTE falta ou pode ser melhorado (sugestões como hipóteses a verificar). Termine com uma lista de 3 a 5 verificações sugeridas.")
    else:
        tarefa = ("Redija um RASCUNHO de dois blocos para o laudo: (1) 'Metodologia' (Método Comparativo Direto, regressão linear múltipla, tamanho da amostra e variáveis do modelo) e "
                  "(2) 'Análise do modelo' (R², R² ajustado, significância, pressupostos). Marque colchetes [CONFERIR] onde o engenheiro deve confirmar algo que não está nos dados (ex.: data de referência, grau de fundamentação).")
    return base + tarefa + "\n\nDADOS:\n" + json.dumps(dados, ensure_ascii=False)


async def gerar_texto(tipo: str, dados) -> tuple[str, list[str]]:
    txt = (await _gemini([{"text": montar_prompt_texto(tipo, dados)}], json_mode=False)).strip()[:5000]
    return txt, numeros_fora(txt, dados)
