# GRAHL Perícias

Aplicativo Streamlit (`app.py`) para gestão de perícias e, agora, um **processador em lote de PDFs**
(`extract_batch.py`) para extrair dados de vários arquivos de uma só vez — inclusive PDFs grandes
(testado para arquivos na faixa de dezenas de MB) e PDFs escaneados (via OCR).

Configuração do app web: veja [`docs/configuracao-local.md`](docs/configuracao-local.md).

---

## Extração de dados de PDFs em lote

### Como funciona (resumo)

1. Você coloca os PDFs em `data/input/`.
2. Roda `python extract_batch.py`.
3. Para **cada PDF**, o script:
   - valida o arquivo (assinatura `%PDF-`, tamanho máximo);
   - lê **página por página** (não carrega o arquivo inteiro na memória);
   - tenta primeiro o **texto nativo** do PDF;
   - se a página tiver pouco ou nenhum texto (página escaneada/imagem), aplica **OCR** só naquela página;
   - extrai os campos por regras (número do processo, vara, partes, CPF, CNPJ, valor da causa, datas...);
   - grava **um JSON** em `data/output/`.
4. Cada PDF roda isolado em um subprocesso com **tempo limite**: se um arquivo travar ou der erro,
   ele é marcado como falha, copiado para `data/failed/` e o lote **continua** com os próximos.
5. No final, é gerado um **relatório do lote** em `data/logs/`.

As pastas `data/input/`, `data/output/`, `data/logs/` e `data/failed/` são **criadas automaticamente**
na primeira execução — não é preciso criar nada manualmente. Elas estão no `.gitignore`, para que
PDFs e dados sensíveis **não** sejam enviados ao GitHub.

### 1. Instalação (uma única vez)

Requisitos: Python 3.10 ou superior.

```bash
# dentro da pasta do projeto
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

**OCR (necessário apenas para PDFs escaneados):** instale também o programa **Tesseract OCR** com o
idioma português:

| Sistema | Comando / procedimento |
|---|---|
| Windows | Baixe o instalador em <https://github.com/UB-Mannheim/tesseract/wiki>. Na instalação, marque **Additional language data → Portuguese**. Depois, se o comando `tesseract --version` não funcionar no terminal, defina `set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe` |
| Ubuntu/Debian | `sudo apt install tesseract-ocr tesseract-ocr-por` |
| macOS | `brew install tesseract tesseract-lang` |

Para conferir: `tesseract --list-langs` deve mostrar `por`.

> Sem o Tesseract o lote **funciona normalmente** para PDFs com texto; apenas as páginas escaneadas
> ficam sem texto e o log mostra um aviso claro explicando o motivo.

### 2. Onde colocar os PDFs

Copie os arquivos para `data/input/` (se a pasta ainda não existir, rode `python extract_batch.py`
uma vez que ela é criada). Subpastas só são lidas com a opção `--recursive`.

### 3. Como rodar

```bash
python extract_batch.py
```

Opções úteis:

| Opção | Para que serve |
|---|---|
| `--input PASTA` / `--output PASTA` | usar outras pastas de entrada/saída |
| `--recursive` | ler PDFs também em subpastas de `data/input/` |
| `--skip-existing` | pular PDFs que já têm JSON com sucesso (ótimo para retomar um lote interrompido) |
| `--no-ocr` | desligar o OCR (mais rápido; só texto nativo) |
| `--timeout 3600` | tempo máximo por PDF em segundos (padrão 1800 = 30 min; `0` = sem limite) |
| `--max-ocr-pages 1000` | máximo de páginas com OCR por PDF (padrão 500) |
| `--ocr-dpi 200` | resolução do OCR (menor = mais rápido; padrão 300) |
| `--no-text` | não incluir o texto das páginas no JSON (apenas os campos) |
| `-v` | log detalhado |

Veja todas com `python extract_batch.py --help`.

As mesmas configurações podem ser feitas por **variáveis de ambiente**:

| Variável | Padrão | Descrição |
|---|---|---|
| `BATCH_DATA_DIR` | `data` | pasta base (dentro dela: `input`, `output`, `logs`, `failed`) |
| `BATCH_INPUT_DIR`, `BATCH_OUTPUT_DIR`, `BATCH_LOGS_DIR`, `BATCH_FAILED_DIR` | — | sobrescrevem cada pasta individualmente |
| `BATCH_OCR_ENABLED` | `1` | `0` desativa o OCR |
| `BATCH_OCR_LANG` | `por` | idioma(s) do Tesseract (ex.: `por+eng`) |
| `BATCH_OCR_DPI` | `300` | resolução do OCR |
| `BATCH_OCR_PAGE_TIMEOUT` | `120` | tempo máximo de OCR por página (s) |
| `BATCH_MAX_OCR_PAGES` | `500` | máximo de páginas com OCR por PDF |
| `BATCH_MIN_CHARS_PER_PAGE` | `50` | abaixo disso a página é tratada como imagem |
| `BATCH_FILE_TIMEOUT` | `1800` | tempo máximo por PDF (s); `0` = sem limite |
| `BATCH_MAX_FILE_SIZE_MB` | `200` | tamanho máximo aceito por PDF |
| `BATCH_MAX_PAGES` | `3000` | máximo de páginas lidas por PDF |
| `BATCH_MAX_TEXT_CHARS` | `5000000` | limite de texto gravado no JSON (os campos continuam sendo extraídos) |
| `BATCH_INCLUDE_TEXT` | `1` | `0` não grava o texto das páginas |
| `BATCH_SKIP_EXISTING` | `0` | `1` pula PDFs já processados com sucesso |
| `BATCH_COPY_FAILED` | `1` | `0` não copia PDFs com falha para `data/failed/` |
| `BATCH_USE_SUBPROCESS` | `1` | `0` roda tudo no mesmo processo (sem timeout real; só para depuração) |
| `TESSERACT_CMD` | — | caminho do executável do Tesseract (Windows) |

Código de saída: `0` = nenhuma falha; `1` = ao menos um PDF falhou; `2` = erro de configuração.

### 4. Como ler os resultados

**`data/output/<nome-do-pdf>.json`** — um arquivo por PDF:

```json
{
  "arquivo_origem": "PARTE_1.pdf",
  "status": "sucesso",
  "inicio_processamento": "2026-09-29T17:00:00-03:00",
  "fim_processamento": "2026-09-29T17:02:10-03:00",
  "duracao_segundos": 130.4,
  "tipo_pdf": "misto",
  "metodo_extracao": "misto",
  "ocr": {"habilitado": true, "disponivel": true, "idioma": "por", "paginas_ocr": 12},
  "paginas_total": 850,
  "paginas_processadas": 850,
  "total_caracteres": 912345,
  "avisos": [],
  "erros": [],
  "campos_extraidos": {
    "processo_num": {"valor": "0001234-56.2023.5.09.0663", "pagina": 1},
    "reclamante_nome": {"valor": "JOAO DA SILVA", "pagina": 1},
    "orgao_julgador": {"valor": null, "pagina": null},
    "cpfs_encontrados": {"valor": ["123.456.789-09"], "paginas": [1]}
  },
  "paginas": [{"numero": 1, "metodo": "texto", "caracteres": 2345, "texto": "..."}]
}
```

- `status`: `sucesso` (tudo ok), `parcial` (extraiu, mas com avisos — ex.: páginas escaneadas sem OCR,
  limite de páginas atingido) ou `falha` (nada extraído; veja `erros`).
- `tipo_pdf`: `texto` (PDF digital), `imagem` (escaneado) ou `misto`.
- `metodo_extracao`: `texto`, `ocr`, `misto` ou `nenhum`.
- `campos_extraidos`: cada campo traz `valor` e a `pagina` onde foi encontrado (`null` = não encontrado).
  Os nomes seguem as chaves já usadas no app (`processo_num`, `orgao_julgador`, `data_autuacao`,
  `valor_causa`, `rito_processual`, `reclamante_nome`, `reclamada_nome`, `reclamante_cpf`,
  `reclamada_cnpj`) + listas de apoio (`processos_encontrados`, `cpfs_encontrados`, `cnpjs_encontrados`).
- `paginas`: texto de cada página e o método usado nela.

**`data/logs/extracao_AAAAMMDD_HHMMSS.log`** — log completo da execução, com progresso `[3/10]`,
página atual de arquivos grandes, avisos e erros (o mesmo que aparece na tela).

**`data/logs/relatorio_lote_AAAAMMDD_HHMMSS.json`** — resumo do lote: totais de sucesso/parcial/falha,
configuração usada e uma linha por arquivo.

**`data/failed/`** — cópia dos PDFs que falharam (o original permanece em `data/input/`).

### 5. Solução de problemas (OCR)

| Mensagem no log | O que fazer |
|---|---|
| `OCR INDISPONÍVEL: Pacote Python 'pytesseract' não instalado` | `pip install -r requirements.txt` |
| `OCR INDISPONÍVEL: Programa 'tesseract' não encontrado` | instale o Tesseract (tabela acima). No Windows, defina `TESSERACT_CMD` com o caminho do `tesseract.exe` |
| `Idioma(s) OCR por não instalado(s)` | instale o pacote de idioma português (`tesseract-ocr-por` / opção *Portuguese* no instalador do Windows). Enquanto isso o OCR usa `eng` |
| `Tempo limite de ... excedido` | aumente `--timeout` (ex.: `--timeout 3600`) ou reduza `--ocr-dpi 200` |
| `... página(s) ... não passaram por OCR: limite de páginas com OCR atingido` | aumente `--max-ocr-pages` |
| `Subprocesso encerrado inesperadamente ... possível falta de memória` | feche outros programas, use `--ocr-dpi 200`, e rode de novo com `--skip-existing` |
| `Arquivo não possui assinatura de PDF válida` | o arquivo está corrompido ou não é PDF; gere/baixe o PDF novamente |
| OCR lento | é normal (alguns segundos por página). Use `--ocr-dpi 200` ou `--no-ocr` se os PDFs forem digitais |

### 6. Como evoluir as regras de extração

As regras ficam em `batch_extraction/fields.py` (lista `DEFAULT_RULES`). Cada regra tem um nome de
campo e uma ou mais expressões regulares; basta incluir/ajustar itens nessa lista — o restante do
pipeline não precisa mudar. Os testes estão em `tests/test_batch_extraction.py`
(`python -m pytest tests/test_batch_extraction.py`).

Estrutura do código:

```
extract_batch.py              # linha de comando (CLI)
batch_extraction/
  config.py                   # configurações e variáveis BATCH_*
  extractor.py                # leitura página a página, detecção texto x imagem, fallback OCR
  ocr.py                      # verificação e execução do OCR (opcional)
  fields.py                   # regras de extração de campos (evoluem aqui)
  processor.py                # lote, subprocesso com timeout, logs, relatório
```

### 7. Próximos passos (checklist para você)

- [ ] `pip install -r requirements.txt`
- [ ] Instalar o Tesseract com idioma português (só se houver PDFs escaneados) e conferir com `tesseract --list-langs`
- [ ] Rodar `python extract_batch.py` uma vez para criar as pastas
- [ ] Copiar os PDFs (PARTE_1, PARTE_2, PARTE_3...) para `data/input/`
- [ ] Rodar `python extract_batch.py` novamente e acompanhar o progresso na tela
- [ ] Conferir o resumo final e o `relatorio_lote_*.json` em `data/logs/`
- [ ] Abrir os JSONs em `data/output/` e verificar os `campos_extraidos`
- [ ] Para arquivos com `falha` ou `parcial`, ler `erros`/`avisos` e seguir a tabela de solução de problemas; depois rodar com `--skip-existing` para reprocessar só o que faltou
- [ ] Informar quais campos vieram vazios ou errados (com o número da página) para ajustarmos as regras em `batch_extraction/fields.py`

### Limitações conhecidas

- As regras de campos são um ponto de partida (padrões comuns de processos trabalhistas/PJe) e devem
  ser ajustadas com base nos PDFs reais.
- A qualidade do OCR depende da digitalização; o texto via OCR pode conter erros de reconhecimento.
- O OCR é feito em série (uma página por vez) para economizar memória; PDFs com centenas de páginas
  escaneadas podem levar vários minutos.
- Tabelas são extraídas como texto corrido (não há reconstrução de tabelas).
