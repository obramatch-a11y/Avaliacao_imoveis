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
