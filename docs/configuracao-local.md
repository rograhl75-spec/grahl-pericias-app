# Configuração local e teste rápido

1. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` apenas localmente e preencha `anthropic`, `firebase` e `[app]`.
2. Nunca versione o `secrets.toml` real; em produção, configure os mesmos valores nos secrets da plataforma de hospedagem.
3. Para uma verificação local rápida, execute `python -m unittest discover -s tests`.
4. Limitação atual: PDFs escaneados ainda dependem de texto pesquisável; OCR ainda não foi implementado.
