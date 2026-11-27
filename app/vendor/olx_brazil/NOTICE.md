# Componentes de terceiros

- `parsers.py`: derivado de `olx_brazil/parsers.py` de https://github.com/omkarcloud/olx-brazil-scraper
  (commit 1ef39e5), MIT, Copyright (c) 2026 Chetan Jain. Licença em `LICENSE`.
- Apenas o código de leitura (funções puras). O transporte do projeto original (imitação de TLS de navegador,
  rotação de perfis e proxies) **não** foi incorporado e não deve ser.

As páginas HTML em `tests/fixtures/olx_*.html` usadas nos testes também vêm do mesmo projeto (MIT, © 2026 Chetan Jain).
