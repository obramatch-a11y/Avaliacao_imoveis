"""Login com Google (Google Identity Services), sessão assinada e cofre de chaves por usuário.

Variáveis de ambiente (todas opcionais; sem elas o app continua funcionando sem login):
  GOOGLE_CLIENT_ID       ID do cliente OAuth (público) criado no Google Cloud
  SESSION_SECRET         texto longo e aleatório; assina a sessão e deriva a chave de criptografia
  FIREBASE_SERVICE_ACCOUNT   JSON da conta de serviço do Firebase (Firestore guarda as chaves já criptografadas)
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
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

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
    return bool(login_disponivel() and _conta_servico())


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


# ---------- Firestore (plano gratuito do Firebase), acessado pelo servidor com conta de serviço ----------
_TOKEN: dict = {"v": None, "exp": 0.0}


def _arquivos_candidatos() -> list[str]:
    """Qualquer .json em /etc/secrets (Secret Files do Render), seja qual for o nome do arquivo."""
    import glob
    lista = [os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE") or "", "/etc/secrets/firebase.json"]
    lista += sorted(glob.glob("/etc/secrets/*.json")) + sorted(glob.glob("/etc/secrets/*firebase*"))
    vistos, saida = set(), []
    for c in lista:
        if c and c not in vistos:
            vistos.add(c)
            saida.append(c)
    return saida


def _conta_servico() -> dict | None:
    bruto = (os.getenv("FIREBASE_SERVICE_ACCOUNT") or "").strip()
    if not bruto:
        # Alternativa: "Secret File" do Render (arquivo firebase.json), sem precisar abrir ou copiar o conteúdo
        for caminho in _arquivos_candidatos():
            try:
                if os.path.isfile(caminho):
                    bruto = open(caminho, encoding="utf-8").read().strip()
                    if bruto:
                        break
            except OSError:
                continue
    if not bruto:
        return None
    try:
        d = json.loads(bruto)
    except ValueError:
        return None
    return d if all(d.get(k) for k in ("client_email", "private_key", "project_id")) else None


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _jwt_servico(d: dict) -> str:
    agora = int(time.time())
    cab = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    cor = _b64(json.dumps({
        "iss": d["client_email"], "scope": "https://www.googleapis.com/auth/datastore",
        "aud": "https://oauth2.googleapis.com/token", "iat": agora, "exp": agora + 3600,
    }).encode())
    chave = serialization.load_pem_private_key(d["private_key"].encode(), password=None)
    assin = chave.sign(f"{cab}.{cor}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{cab}.{cor}.{_b64(assin)}"


async def _token_acesso(cli: httpx.AsyncClient, d: dict) -> str | None:
    if _TOKEN["v"] and _TOKEN["exp"] > time.time() + 60:
        return _TOKEN["v"]
    r = await cli.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": _jwt_servico(d)})
    if r.status_code != 200:
        return None
    j = r.json()
    _TOKEN["v"], _TOKEN["exp"] = j.get("access_token"), time.time() + int(j.get("expires_in", 3000))
    return _TOKEN["v"]


def _doc_url(d: dict, sub: str) -> str:
    return f"https://firestore.googleapis.com/v1/projects/{d['project_id']}/databases/(default)/documents/chaves_usuario/{sub}"


async def _chamar(metodo: str, sub: str, corpo: dict | None = None):
    d = _conta_servico()
    if not d or not sub.isdigit():
        return None
    async with httpx.AsyncClient(timeout=10.0) as cli:
        tk = await _token_acesso(cli, d)
        if not tk:
            return None
        return await cli.request(metodo, _doc_url(d, sub), headers={"Authorization": f"Bearer {tk}"}, json=corpo)


async def guardar_chave(sub: str, email: str, chave: str) -> bool:
    if not cofre_disponivel():
        return False
    try:
        r = await _chamar("PATCH", sub, {"fields": {
            "email": {"stringValue": email}, "chave_cifrada": {"stringValue": cifrar(chave)},
            "atualizado": {"timestampValue": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}}})
        return bool(r is not None and r.status_code == 200)
    except Exception:
        return False


async def buscar_chave(sub: str) -> str | None:
    if not cofre_disponivel():
        return None
    try:
        r = await _chamar("GET", sub)
        if r is None or r.status_code != 200:
            return None
        return decifrar(r.json()["fields"]["chave_cifrada"]["stringValue"])
    except Exception:
        return None


async def remover_chave(sub: str) -> bool:
    if not cofre_disponivel():
        return False
    try:
        r = await _chamar("DELETE", sub)
        return bool(r is not None and r.status_code in (200, 404))
    except Exception:
        return False


def motivo_sem_cofre() -> str:
    """Explica, sem expor segredos, por que o cofre não está ativo (ajuda a corrigir a configuração)."""
    if not login_disponivel():
        return "login_nao_configurado"
    bruto = (os.getenv("FIREBASE_SERVICE_ACCOUNT") or "").strip()
    origem = "variavel" if bruto else ""
    if not bruto:
        for caminho in _arquivos_candidatos():
            if caminho and os.path.isfile(caminho):
                try:
                    bruto, origem = open(caminho, encoding="utf-8").read().strip(), "arquivo"
                except OSError:
                    return "arquivo_ilegivel"
                break
    if not bruto:
        return "sem_arquivo_nem_variavel"
    try:
        d = json.loads(bruto)
    except ValueError:
        return f"json_invalido_{origem}"
    faltam = [k for k in ("client_email", "private_key", "project_id") if not d.get(k)]
    if faltam:
        return "campos_ausentes:" + ",".join(faltam)
    try:
        serialization.load_pem_private_key(d["private_key"].encode(), password=None)
    except Exception:
        return "chave_privada_invalida"
    return "ok"
