# Inferência Estatística

Aplicativo web para coleta, padronização e saneamento de amostras de mercado imobiliário com exportação em **CSV** e aderente às boas práticas da **ABNT NBR 14653-2**.

## Como rodar localmente
```bash
python -m venv .venv
source .venv/bin/activate  # No Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Acesse `http://127.0.0.1:8000`.

## Rodar testes
```bash
pytest
```

## Login com Google e cofre de chaves (opcional)

Sem estas variáveis o app funciona normalmente, só sem login.

| Variável | Para quê |
|---|---|
| `GOOGLE_CLIENT_ID` | ID do cliente OAuth (tipo "Aplicativo da Web") criado no Google Cloud. Em "Origens JavaScript autorizadas" coloque a URL do app. |
| `SESSION_SECRET` | Texto aleatório com 24+ caracteres. Assina a sessão e deriva a criptografia das chaves. |
| `FIREBASE_SERVICE_ACCOUNT` (ou Secret File `firebase.json` no Render) | JSON inteiro da conta de serviço do Firebase (Configurações do projeto → Contas de serviço → Gerar nova chave privada). O Firestore (plano gratuito) guarda as chaves, já criptografadas, na coleção `chaves_usuario`. |
