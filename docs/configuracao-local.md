# Configuração local e teste rápido

1. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` apenas localmente e preencha a seção `[firebase]`.
2. Nunca versione o `secrets.toml` real; em produção, configure os mesmos valores nos secrets da plataforma de hospedagem.
3. Instale as dependências com `pip install -r requirements.txt`.
4. Para executar todos os testes, use `python -m pytest tests`.
5. Inicie o app com `streamlit run app.py`. O cadastro permite preenchimento manual ou importação opcional de um documento Word (`.docx`).

## Fluxo extrajudicial (manual, sem IA)

- Selecione o módulo previdenciário no cadastro. Casos novos não recebem riscos, equivalência histórica ou conclusão favorável presumidos.
- Na edição, preencha identificação do estabelecimento (CNAE/grau de risco), natureza/modo temporal, responsável/conselho/ART aplicável, períodos CNIS, APR **presumida**, planejamento, profissiografia real e avaliações **observadas**. Cada avaliação ambiental referencia um `periodo_id` único e estável do CNIS.
- Data, horário, presença, declarações, medições e fotos permanecem na tela compartilhada de diligência, com os mesmos recursos de câmera, GPS, voz e rascunho local.
- Salve rascunhos incompletos. Para o documento final, registre os dados necessários, metodologia, fontes e conclusão escrita pelo profissional; laudos extemporâneos/mistos exigem evidências históricas e fundamentação. Depois de salvar, confirme a revisão dos **dados salvos** e clique em **Registrar revisão profissional**. Alterações nos dados/evidências, inclusive medições e fotos, invalidam a revisão.
- A tela de documentos permite relatório pré-pericial/checklist sem aprovação, identificado como **rascunho**, ou LTCAT revisado com períodos, registros ambientais, vistoria e fotos. O anexo PPP é **apoio técnico estruturado, não PPP oficial assinado**, nem reconhecimento automático de tempo especial. Não há assinatura digital ou protocolo automático.
- Casos antigos conservam seus textos e períodos legados; não há conversão automática do período livre em CNIS. Dados judiciais e recursos compartilhados não são remodelados.

## Importação revisada e formatos

No cadastro, o DOCX é opcional: visualizar não altera os campos; clique em **Usar campos reconhecidos no novo caso** e revise antes de criar. Na edição extrajudicial, importe DOCX, CSV ou JSON em **Importar e revisar antes de aplicar**. Veja a prévia, selecione campos (nenhum selecionado por padrão), confirme a substituição e aplique. Uma tabela selecionada substitui a tabela inteira, não mescla linhas. IDs, `_revision`, fotos e aprovação profissional não são importados. O salvamento mantém a transação/revisão existente; falhas não são tratadas como sucesso.

DOCX comuns usam somente rótulos/tags reconhecidos pelo parser existente: não há interpretação por IA. Campos ausentes/vazios desse parser são ignorados. Documentos gerados incluem bloco estruturado para reimportação exata, inclusive valores vazios e `false`. JSON exportado na edição usa `{"schema": "grahl-extrajudicial-v1", "dados": {...}}`; contém campos reconhecidos e tabelas, sem fotos ou revisão. Esses formatos não substituem backup integral do caso.

### CSV CNIS

UTF-8 (BOM opcional), separador **vírgula**, cabeçalho obrigatório nesta ordem, sem colunas extras:

```csv
periodo_id,inicio,fim,empresa,cnpj,condicao,cargo,setor,atividade
P1,2020-01-01,2021-12-31,Empresa exemplo,11222333000144,CLT,Mecânico,Manutenção,Reparo de máquinas
```

Datas `AAAA-MM-DD`; `fim` vazio significa período em aberto. `periodo_id`, `inicio`, `empresa`, `condicao`, `cargo`, `setor` e `atividade` são obrigatórios por linha. `periodo_id` deve ser único. Condição: `CLT`, `Autônomo`, `Cooperado`, `Outro` ou `Não informado`. CNPJ opcional com 14 dígitos (pontuação aceita; a validação não verifica dígitos de controle nem consulta cadastro). Vírgulas dentro de valores exigem aspas CSV. CSV vazio, datas inválidas, fim anterior ao início ou esquema incorreto são rejeitados, sem salvar.

### Registros ambientais no JSON / editor

Colunas: `periodo_id,tipo,agente,intensidade,unidade,metodo,fonte,via,exposicao,epc,epi,ca,responsavel,conselho,instrumento,calibracao`.

`tipo`: `F`, `Q` ou `B`; `epc`/`epi` representam eficácia, com `Sim`, `Não` ou `Não informado`. Registre agente, método, fonte, via e exposição; responsável/conselho são necessários para revisão final de cada registro. Intensidade/unidade podem permanecer vazias quando a avaliação é qualitativa, conforme justificativa profissional. Instrumento/calibração e CA devem ser preenchidos quando aplicáveis. Não há cálculo automático de eficácia, enquadramento legal ou equivalência.

Não há integração de importação PDF/CNIS por OCR neste fluxo.
