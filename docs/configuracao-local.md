# Configuração local e teste rápido

1. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` apenas localmente e preencha `anthropic`, `firebase` e `[app]`.
   - Em `[app]`, ajuste também `usd_brl_exchange_rate` para a cotação USD→BRL usada na estimativa e no custo real.
   - Limites da importação de PDFs: `max_pdf_pages_total` (padrão 3000) e `max_pdf_chars_total` (padrão 1.200.000). O padrão de caracteres coincide com a capacidade da Claude (`claude_chunk_chars` × `claude_max_chunks` = 120.000 × 10); não configure acima desse produto. Se os PDFs ultrapassarem o limite, a importação é bloqueada com mensagem na própria tela e o processo não é alterado — divida o processo em lotes menores (por exemplo, importe `PARTE_1` e `PARTE_2` separadamente). Reduza os valores se a instância do Streamlit Cloud ficar sem memória.
2. Nunca versione o `secrets.toml` real; em produção, configure os mesmos valores nos secrets da plataforma de hospedagem.
3. Para uma verificação local rápida, execute `python -m unittest discover -s tests`.
4. Limitação atual: na importação pelo app, PDFs escaneados ainda dependem de texto pesquisável. Para extrair vários PDFs (inclusive escaneados, com OCR), use o processamento em lote `python extract_batch.py` descrito no `README.md`.
