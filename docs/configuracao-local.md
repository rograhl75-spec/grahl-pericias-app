# Configuração local e teste rápido

1. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` apenas localmente e preencha `anthropic`, `firebase` e `[app]`.
   - Em `[app]`, ajuste também `usd_brl_exchange_rate` para a cotação USD→BRL usada na estimativa e no custo real.
   - Limites da importação de PDFs: `max_pdf_pages_total` (padrão 3000) e `max_pdf_chars_total` (padrão 1.200.000). O padrão de caracteres coincide com a capacidade da Claude (`claude_chunk_chars` × `claude_max_chunks` = 120.000 × 10); não configure acima desse produto. Se os PDFs ultrapassarem o limite, a importação única é bloqueada com mensagem na própria tela e o processo não é alterado. Reduza os valores se a instância do Streamlit Cloud ficar sem memória.
   - Importação em lotes (`pdf_batch_import_enabled`, padrão `true`; `max_pdf_batches`, padrão 4): quando o limite acima é ultrapassado, a tela oferece o botão **🧩 Processar em lotes**. Nada é processado automaticamente; o usuário precisa escolher esse modo.
     - Os PDFs são divididos por intervalos de páginas (um arquivo grande, como `PARTE_1.PDF`, pode ocupar mais de um lote) em até `max_pdf_batches` lotes de no máximo `max_pdf_chars_total` caracteres. Nunca há truncamento: uma página maior que o lote, ou a necessidade de mais lotes que o permitido, bloqueia a importação.
     - Antes de começar, a cota diária de chamadas (`max_api_calls_per_day`) e de custo (`cost_limit_per_day`) é validada para o total estimado. Antes de cada lote, ela é validada de novo e reservada para aquele lote. Cada lote costuma usar vários chunks mais a consolidação interna da Claude (cerca de 16 chamadas para 1.200.000 caracteres).
     - Os lotes são processados em sequência, com barra de progresso (lote atual, total e arquivos/páginas). O texto de cada lote é descartado logo após a análise e nunca fica em `st.session_state`.
     - Os resultados são mesclados localmente, sem chamada extra à Claude:
       - campos de identificação (processo, partes, datas, valores): vale o primeiro lote que informou o campo;
       - fase processual e dados da vistoria: vale o último lote;
       - campos descritivos: valores distintos são concatenados;
       - EPIs: sem duplicidade;
       - `fontes`: preserva as referências de cada lote (ou o intervalo de páginas do lote quando a Claude não informou fonte).
       Valores divergentes aparecem em "Divergências entre lotes" para revisão.
     - O processamento em lotes ocorre em uma única execução do Streamlit; não interaja com a página até a barra de progresso terminar. Os testes automatizados usam mocks. A validação real com Anthropic, Firestore e Streamlit Cloud só é possível após o deploy.
     - Se qualquer lote falhar, a tela mostra o lote e os arquivos/páginas envolvidos. Nenhum registro de importação é criado e o processo não é alterado. Use **🔁 Tentar novamente em lotes** (recomeça do primeiro lote) ou **🗑️ Descartar importação em lotes**.
2. Nunca versione o `secrets.toml` real; em produção, configure os mesmos valores nos secrets da plataforma de hospedagem.
3. Para uma verificação local rápida, execute `python -m unittest discover -s tests`.
4. Limitação atual: na importação pelo app, PDFs escaneados ainda dependem de texto pesquisável. Para extrair vários PDFs (inclusive escaneados, com OCR), use o processamento em lote `python extract_batch.py` descrito no `README.md`.
