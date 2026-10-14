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

## Seleção de casos e fotos de campo

O seletor lateral usa o ID do caso (também guardado na URL como `?caso=`); a pesquisa apenas filtra a lista. Gravações só são aceitas para o caso ativo. Fotos capturadas entram numa fila de pendentes do próprio caso, e câmera/uploader são liberados após cada gravação. Falhas mantêm as pendentes. Fotos novas ficam no Firebase Storage; o documento Firestore continua limitado a 1 MiB para textos, metadados e fotos legadas. Detalhes e checklist de campo: `docs/auditoria-integridade-campo.md`.

### Firebase Storage (fotos novas)

1. No mesmo projeto Firebase, habilite o Storage e crie/confirme o bucket. Confira no Console os requisitos de faturamento/plano (Blaze quando exigido), preços e região antes de habilitar: armazenamento, operações e tráfego/downloads podem ser cobrados. Configure alertas de orçamento; alertas não são um teto automático de gasto.
2. Em `[firebase]`, além da service account já usada no Firestore, configure `storage_bucket` com o **nome exato** mostrado no Console, por exemplo `seu-projeto.firebasestorage.app` ou `seu-projeto.appspot.com`. Não use `gs://`, URL nem caminho. Alternativamente defina `FIREBASE_STORAGE_BUCKET` no servidor (tem precedência). O app não adivinha nem cria o bucket.
3. A mesma service account precisa de IAM para ler, criar e consultar objetos nesse bucket (por exemplo, papéis **Storage Object Creator** e **Storage Object Viewer**, limitados ao bucket). O app não precisa excluir objetos. Mantenha o bucket privado; não habilite leitura pública nem gere tokens públicos. O Admin SDK executa no servidor e usa IAM, não as regras de acesso do SDK cliente. Não configure acesso público como solução para erro de permissão.
4. Reinicie o servidor após alterar a configuração do bucket. Nenhum segredo adicional é necessário; nunca versione a chave privada nem o arquivo real de secrets.

Cada foto nova é comprimida como antes e enviada a `campo_fotos/<SHA-256 do ID do caso>/<SHA-256 do conteúdo>.<extensão>`. A identidade é calculada sobre os bytes comprimidos; reenvios desse conteúdo no mesmo caso reutilizam o objeto. O campo `campo_fotos` guarda só `storage_path`, `hash`, `mime_type`, `size_bytes`, `created_at` (UTC), `gps` e `legenda`. Não há base64 novo no Firestore nem URL pública/assinada persistida. As referências usam o bucket configurado: mudar de bucket exige preservar/copiar os objetos e validar as referências antes, não apenas trocar o nome.

A galeria e todos os exportadores Word leem pelo Admin SDK. A leitura usa cache de cinco minutos (até 32 fotos) para reduzir downloads em reruns. Fotografias legadas com `base64` ou `path` continuam sendo lidas, sem regravação/migração automática; caminhos legados precisam continuar acessíveis no servidor. URLs arbitrárias no documento não são baixadas.

O limite de 1 MiB do Firestore **não aumentou**: os bytes novos ficam fora dele, mas muitos metadados ou base64 legado ainda podem esgotar o documento. A barra da tela estima somente o documento (com orçamento conservador de 1.000.000 bytes), não o uso total do bucket. Cada foto tem teto de 10 MiB após compressão, além dos limites de upload/memória da hospedagem. Envie lotes pequenos para evitar tempo de execução, tráfego e custos excessivos.

Só há confirmação de sucesso após o upload **e** a gravação transacional do caso. Falhas conservam as pendentes na sessão; em lote parcial, apenas as fotos vinculadas saem da fila. Se houver conflito de revisão, recarregue a versão da nuvem e tente novamente. A fila não é backup: fechar/recarregar a página pode perdê-la. Um upload concluído antes de falhar o Firestore pode deixar objeto sem referência, reutilizado no reenvio.

Excluir fotos/casos ou descartar pendentes **não apaga objetos do Storage**. Isso evita remover evidências de produção ou objetos reutilizados por reenvios. Retenção/limpeza deve ser planejada pelo administrador com backup e conferência das referências; não aplique exclusão automática/lifecycle indiscriminada que quebre fotos ainda vinculadas.

Validação de implantação (caso sintético, sem dados reais): envie dois lotes, repita uma foto, recarregue e confira galeria/legendas e Word; confirme que o JSON novo contém `storage_path` sem `base64`. Abra também um caso legado e exporte o Word. Simule indisponibilidade/permissão negada e confira as pendentes. Os testes automatizados usam bucket e Firestore simulados; não comprovam IAM, faturamento nem conectividade de produção.
