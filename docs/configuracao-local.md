# Configuração local e teste rápido

1. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` apenas localmente e preencha `anthropic`, `firebase` e `[app]`.
   - Em `[app]`, ajuste também `usd_brl_exchange_rate` para a cotação USD→BRL usada na estimativa e no custo real.
2. Nunca versione o `secrets.toml` real; em produção, configure os mesmos valores nos secrets da plataforma de hospedagem.
3. Para uma verificação local rápida, execute `python -m unittest discover -s tests`.
4. Limitação atual: na importação pelo app, PDFs escaneados ainda dependem de texto pesquisável. Para extrair vários PDFs (inclusive escaneados, com OCR), use o processamento em lote `python extract_batch.py` descrito no `README.md`.
