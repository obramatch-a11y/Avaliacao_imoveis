"""Login com Google (Google Identity Services), sessão assinada e cofre de chaves por usuário.

Variáveis de ambiente (todas opcionais; sem elas o app continua funcionando sem login):
  GOOGLE_CLIENT_ID       ID do cliente OAuth (público) criado no Google Cloud
  SESSION_SECRET         texto longo e aleatório; assina a sessão e deriva a chave de criptografia
  SUPABASE_URL / SUPABASE_SERVICE_KEY   onde as chaves (já criptografadas) ficam guardadas
"""
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone

import httpx
from cryptography.fernet import Fernet, InvalidToken

COOKIE = "ie_sessao"
DURACAO = 30 * 24 * 3600


def _segredo() -> bytes | None:
    s = (os.getenv("SESSION_SECRET") or "").strip()
    return s.encode() if len(s) >= 24 else None


def client_id() -> str:
    return (os.getenv("GOOGLE_CLIENT_ID") or "").strip()


def login_disponivel() -> bool:
    return bool(client_id() and _segredo())


def cofre_disponivel() -> bool:
    return bool(login_disponivel() and os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))


# ---------- sessão assinada ----------
def criar_sessao(usuario: dict) -> str:
    corpo = base64.urlsafe_b64encode(json.dumps({**usuario, "exp": int(time.time()) + DURACAO}).encode()).decode()
    assin = hmac.new(_segredo() or b"", corpo.encode(), hashlib.sha256).hexdigest()
    return f"{corpo}.{assin}"


def ler_sessao(cookie: str | None) -> dict | None:
    seg = _segredo()
    if not cookie or not seg or "." not in cookie:
        return None
    corpo, assin = cookie.rsplit(".", 1)
    esperado = hmac.new(seg, corpo.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(assin, esperado):
        return None
    try:
        dados = json.loads(base64.urlsafe_b64decode(corpo.encode()))
    except ValueError:
        return None
    return dados if dados.get("exp", 0) > time.time() and dados.get("sub") else None


# ---------- verificação do token do Google ----------
async def verificar_google(credencial: str) -> dict | None:
    """Confere o token de login com o Google e devolve {sub, email, nome} se for válido para este app."""
    if not login_disponivel() or not credencial or len(credencial) > 4096:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": credencial})
    except Exception:
        return None
    if r.status_code != 200:
        return None
    j = r.json()
    if j.get("aud") != client_id() or j.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        return None
    if str(j.get("email_verified")).lower() != "true" or not j.get("sub"):
        return None
    return {"sub": j["sub"], "email": j.get("email", ""), "nome": j.get("name") or j.get("email", "")}


# ---------- cofre (chave criptografada por usuário) ----------
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"cofre|" + (_segredo() or b"")).digest()))


def cifrar(chave: str) -> str:
    return _fernet().encrypt(chave.encode()).decode()


def decifrar(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def _cab() -> dict:
    k = os.getenv("SUPABASE_SERVICE_KEY", "")
    return {"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json"}


def _url() -> str:
    return os.getenv("SUPABASE_URL", "").rstrip("/") + "/rest/v1/chaves_usuario"


async def guardar_chave(sub: str, email: str, chave: str) -> bool:
    if not cofre_disponivel():
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.post(
                _url(), params={"on_conflict": "sub"},
                headers={**_cab(), "Prefer": "resolution=merge-duplicates"},
                json={"sub": sub, "email": email, "chave_cifrada": cifrar(chave), "atualizado": datetime.now(timezone.utc).isoformat()},
            )
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


async def buscar_chave(sub: str) -> str | None:
    if not cofre_disponivel():
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.get(_url(), params={"sub": f"eq.{sub}", "select": "chave_cifrada"}, headers=_cab())
        linhas = r.json() if r.status_code == 200 else []
    except Exception:
        return None
    return decifrar(linhas[0]["chave_cifrada"]) if linhas else None


async def remover_chave(sub: str) -> bool:
    if not cofre_disponivel():
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.delete(_url(), params={"sub": f"eq.{sub}"}, headers=_cab())
        return r.status_code in (200, 204)
    except Exception:
        return False
