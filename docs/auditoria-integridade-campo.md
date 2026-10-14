# Auditoria de integridade: seleção de casos e fotos de campo

Escopo: os dois problemas relatados em campo (dados gravados em outro processo; não conseguir
inserir novas fotos depois de salvar) e os fluxos relacionados após os PRs #27 e #28.
A auditoria **não é completa**: cobre o que está listado abaixo. Todas as reproduções usaram
dados sintéticos com banco simulado (mocks/AppTest e um servidor Streamlit local com banco em
memória). **Nada foi validado no Firestore real nem em celular/tablet.** Nenhum registro de
produção foi lido, alterado ou migrado.

## 1. Causas comprovadas por reprodução

### 1.1 Seletor de caso mostrava um caso e o app editava outro (crítico)
- Local: `app.py`, barra lateral (antigo `selectbox(..., index=..., key="caixa_pesquisa")`).
- Evidência: com Streamlit 1.65 (versão instalada por `streamlit>=1.36,<2.0`), a identidade de um
  `selectbox` com `key` depende só da chave; o parâmetro `index` é ignorado depois da primeira
  renderização. Reprodução (AppTest): casos Proc_01/Proc_02 → criar Proc_03. Resultado:
  `processo_ativo = Proc_03`, mas a caixa continuava exibindo **Proc_01**. Ao escolher Proc_01 na
  caixa, o valor do widget não mudava, o `on_change` não disparava e o app **continuava em
  Proc_03**. Tudo o que fosse digitado era gravado em Proc_03.
- O mesmo descompasso ocorre sempre que `processo_ativo` muda fora do seletor (criação,
  exclusão, filtro da pesquisa).
- A pesquisa também trocava o caso ativo sem ação explícita quando o caso atual não
  correspondia ao termo digitado.
- Correção: as opções agora são **IDs estáveis**, com `format_func` para o rótulo. O estado do
  widget é sincronizado com `processo_ativo` antes de instanciá-lo. A pesquisa só filtra a lista e
  mantém o caso ativo visível. O caso escolhido fica na URL (`?caso=Proc_XX`) e é restaurado
  quando a página recarrega ou quando o usuário volta ao app.

### 1.2 Fotos do caso A gravadas no caso B (crítico)
- Local: `app.py`, captura de fotos (`camera_input`/`file_uploader` sem `key`).
- Evidência (AppTest): enviar 2 fotos em Proc_01 e depois mudar a pesquisa (o que trocava o caso
  sem sair da tela de campo) fazia as **2 fotos de Proc_01 serem salvas em Proc_02**. Os widgets
  tinham a mesma identidade em todos os casos e mantinham os arquivos.
- Correção: chaves `camera_{caso}_{versão}` e `fotos_upload_{caso}_{versão}` e fila de pendentes
  separada por caso.

### 1.3 Fotos não liberavam novo ciclo / exclusão não persistia (alto)
- Evidência (AppTest): depois de salvar, o uploader continuava com os arquivos. Ao excluir uma
  foto, o rerun seguinte a **reinseria e salvava de novo**; “Limpar todas” tinha o mesmo
  problema. A câmera mantinha a última captura até o usuário tocar em “Clear photo”. Se a
  gravação falhava, as fotos acrescentadas em memória se perdiam e o app tentava gravar de novo a
  cada rerun, mostrando sempre “Erro Crítico de Rede”.
- Correção: as fotos capturadas entram em uma fila de pendentes do caso e a versão dos widgets
  muda, deixando câmera e uploader vazios para o próximo ciclo. A deduplicação compara com fotos
  salvas e pendentes, e as duplicatas são informadas. Se a gravação falhar, as pendentes são
  mantidas e aparecem os botões “Tentar salvar”, “Recarregar versão da nuvem” e “Descartar”.

### 1.4 Legendas presas ao índice (médio)
- Evidência: as chaves eram `lg_{caso}_{idx}`. Depois de excluir a foto 1, a foto 2 aparecia com
  a legenda da foto excluída, e “Atualizar” gravava a legenda errada.
- Correção: as chaves agora usam a identidade da foto (hash do conteúdo + ocorrência).

### 1.5 Limite de 1 MB por documento (limite legítimo, comunicado)
- As fotos ficam em base64 **dentro** do documento do caso no Firestore, que aceita no máximo
  1 MiB por documento. Medição local de `comprimir_imagem`: até cerca de 90 KB por foto de
  textura densa (cerca de 120 KB em base64). Isso permite aproximadamente 8 a 15 fotos por caso,
  conforme o conteúdo.
- Este limite é **hipótese compatível** com o relato de campo (não foi possível consultar os logs
  de produção). Antes da correção, o usuário via apenas “Erro Crítico de Rede”.
- Correção: o app mostra o armazenamento usado pelo caso e grava as pendentes que cabem. O
  excedente fica pendente com mensagem clara, e a mensagem do banco foi traduzida. **O limite
  continua existindo.** Para ampliá-lo, recomenda-se mover as fotos para Firebase Storage ou para
  uma subcoleção, o que exige ajustar documentos, hash de evidências e compatibilidade com casos
  legados. Essa mudança não foi feita aqui.

## 2. Outras correções no escopo
- **Bloqueio de gravação fora do caso ativo** (`salvar_processo` em `app.py`): qualquer gravação
  cujo destino seja diferente do caso ativo é recusada com mensagem, e nada é salvo. A criação
  usa `novo=True` e recusa um ID que já exista.
- **Identidade visível**: o cabeçalho mostra ID, nome e número. Os placeholders dos campos de
  vistoria, as mensagens e os toasts de gravação também incluem o ID.
- **Rascunho local (navegador) e ditado por voz**: o seletor CSS usava o mesmo placeholder em
  todos os casos. Agora o placeholder inclui o ID do caso, então um iframe antigo não consegue ler
  nem escrever campos de outro caso.
- **Alterações não salvas nos textos da vistoria**: ficam preservadas na sessão **somente para o
  caso de origem**, com aviso na tela e na barra lateral e um botão para descartar. Gravar fotos
  não grava textos não validados, porque a gravação parte do snapshot salvo.
- **GPS por caso** (antes era `gps_field_main`, compartilhado entre casos).
- **EPIs** (`data_editor`) agora têm chave por caso, para que edições não salvas não apareçam em
  outro caso com tabela idêntica.
- **Limpar todas as fotos** exige confirmação.
- **Exclusão**: `excluir_processo` retorna sucesso ou falha, e o estado só é limpo quando a
  exclusão dá certo. Depois de excluir, o app volta para “Novo Processo”.
- **Concorrência**: depois de gravar com sucesso, o `_revision` local é atualizado. O botão
  “Recarregar versão da nuvem” passa a usar a revisão atual sem perder as pendentes. A transação
  do Firestore continua igual.

## 3. Achados auditados e pendentes (não corrigidos)
| Local | Severidade | Achado / impacto |
|---|---|---|
| `app.py` formulários judiciais (`st.form`) | Médio | Alterações não enviadas são descartadas ao trocar de caso ou de tela. Elas nunca vão para outro caso, porque o `form_id` faz parte da identidade dos widgets. Agora há um aviso explícito. |
| `ui/extrajudicial.py` formulário | Médio | Mesmo comportamento: o rascunho só é preservado ao clicar em Salvar. As chaves já usam o prefixo `extra_{id}_` (isolado). |
| `core/database.carregar_dados` | Médio | A revisão esperada fica fixa por sessão. Se o caso for alterado em outro aparelho, as gravações são recusadas até recarregar a página ou usar o botão de recarga (só existe na área de fotos pendentes). |
| `core/database.salvar_processo` | Médio | Grava o documento inteiro (`transaction.set`). Edições simultâneas são barradas pela revisão, mas não são mescladas. |
| Limite de 1 MiB | Alto (operacional) | Ver 1.5. É necessária uma decisão de arquitetura. |
| `components.v1.html` | Baixo | O Streamlit avisa que essa API foi descontinuada (prazo informado: 2026-06-01). O rascunho local, a voz e o GPS dependem dela. |
| `comprimir_imagem` | Baixo | Não aplica a orientação EXIF; fotos de celular podem ficar giradas. |
| `grahl_app/` | Informativo | É um pacote auxiliar usado só nos testes, não pelo `app.py`. |
| Importação Word/CSV/JSON, CNIS, aprovação de revisão, exportação | — | Revisados. As chaves são isoladas por caso e a importação extrajudicial não vaza entre casos (teste). Foto nova invalida a aprovação extrajudicial (teste). Não foram encontrados defeitos novos. |

Registros já gravados no caso errado **não foram alterados**. Para revisão manual: compare em cada
caso suspeito as datas e textos da vistoria e as fotos (pelo conteúdo/GPS) com as anotações de
campo. Corrija manualmente, pelo próprio app, somente depois de confirmar a origem.

## 4. Testes e comandos executados
- `python -m py_compile app.py` — OK.
- `python -m pytest tests` — toda a suíte passou, incluindo os novos
  `tests/test_app_integridade.py` (AppTest) e `tests/test_campo_fotos.py`.
- Navegador real (Chrome headless com o servidor `streamlit run` e banco **em memória**): abrir
  `?caso=Proc_02` restaurou o caso; os placeholders mostraram o ID; dois ciclos de upload
  gravaram 2 fotos e depois +1, com a duplicata ignorada e o uploader vazio após cada gravação.
- Todos esses testes usam mocks ou banco em memória: **não substituem validação no Firestore nem
  em dispositivo móvel**.

## 5. Checklist para validar no celular em campo
1. Crie dois casos sintéticos, “TESTE A” e “TESTE B”, com o mesmo nome de reclamante.
2. Selecione A na barra lateral. Confira se o cabeçalho e o placeholder dos campos mostram o ID de A.
3. Em Diligência, envie 3 fotos. Confira se aparece “Gerenciar Fotos (3 fotos salvas na nuvem)”, se o
   uploader fica vazio e se a área de adição continua aberta para o próximo lote. Feche a área e
   reabra pelo botão grande “➕ Adicionar novas fotos” (fora dos cartões das imagens).
4. Edite a legenda da foto 1 e toque em Atualizar. Depois envie mais 2 fotos (2º ciclo). Confira se
   aparecem 5 fotos, sem duplicatas, e se a legenda da foto 1 foi mantida.
5. Envie de novo uma foto já salva. Deve aparecer o aviso “ignorada”, sem duplicar.
6. Digite um texto em “Pessoas presentes” sem salvar e selecione B. B não deve mostrar esse texto,
   e a barra lateral deve avisar sobre o rascunho de A.
7. Em B, envie 1 foto. Confira se B tem 1 foto e se A continua com 5.
8. Volte para A. O texto não salvo deve reaparecer; salve ou descarte.
9. Recarregue a página ou feche e reabra o navegador. O caso ativo deve continuar o mesmo (URL `?caso=`).
10. Ative o modo avião e envie uma foto. Ela deve ficar como pendente; volte a ficar online e use
    “Tentar salvar”.
11. Observe o quadro “📍 Onde ficam as fotos” (salvas na nuvem × pendentes nesta sessão e espaço do
    caso) perto do limite e confirme se a mensagem é clara.
12. No final, exclua os casos de teste.
