# Motor de preenchimento — reconhecimento e inserção

A melhoria mantém Python/PySide6, o banco e os modelos existentes. Não introduz
serviço de nuvem nem copia código do Text Blaze. O estudo serviu como referência
para separar reconhecimento, preparação, seleção, inserção e confirmação.

## Mudanças

- Cadastro, importação, matcher e recuperação usam `casefold` Unicode. O índice
  ASCII `NOCASE` do SQLite deixa de decidir sozinho qual modelo será expandido.
  Uma colisão Unicode em banco legado é recusada pelo expansor, preservando os
  dois registros em vez de inserir conteúdo arbitrário.
- O hook recebe só atalhos, sem ler HTML/base64. A consulta de um modelo usa seu
  ID e um cache LRU de até 16 itens / 4 milhões de caracteres. `total_changes`,
  `data_version` e estado de transação invalidam alterações locais, externas e
  leituras feitas dentro de transação posteriormente revertida.
- O cache contém o modelo original, não a mensagem pronta. Data/hora, clipboard
  e cursor são resolvidos em cada uso, mantendo os comandos dinâmicos atuais.
- O PowerShell é somente o bootstrap. O loop de UI Automation, validação e JSON
  passa a C# compilado uma vez por processo MTA, ainda isolado da interface.
  O aquecimento não bloqueia a GUI esperando a compilação terminar.
- Para selecionar o atalho antes do caret, o worker procura somente o sufixo no
  intervalo que termina naquele caret. Não procura o prefixo inteiro do documento
  nem usa uma contagem insegura de unidades UIA Character para emoji/acentos.
- Se `Select()` já refletiu a seleção exata, o worker devolve snapshot validado;
  a GUI cola no mesmo turno, sem outra leitura integral. Se o editor ainda mostra
  o caret antigo, recebe ACK e aguarda confirmação, sem selecionar/colar de novo.
- Teams e navegadores identificados usam agora a sequência recém-digitada do
  hook: um lote `SendInput` remove esse sufixo com Backspace e envia Ctrl+V.
  Não há Shift+Left/Ctrl+C nesse caminho. Uma seleção/cópia interceptada pelo
  editor não pode mais bloquear uma expansão. Teclas virtuais levam scan codes.
- O Word desktop usa seu modelo nativo via `AccessibleObjectFromWindow` no
  documento `_WwG` da janela em primeiro plano. O conector STA verifica que
  o intervalo imediatamente anterior ao caret contém literalmente o atalho e
  executa `Range.PasteAndFormat(16)` uma vez, solicitando a formatação original.
  Não muda preferências do Office, não abre arquivos, não executa macros e não
  procura uma instância arbitrária com `GetActiveObject`.
- O conector Word roda fora da GUI. A interface continua atendendo OLE enquanto
  o Word lê os formatos do clipboard. O ACK nativo permite reconhecer a revisão
  causada pela materialização atrasada, mantendo token, conteúdo e contexto.

## Contratos preservados

O hook acompanha janela, controle, teclado e mouse. A rota web só aceita um
candidato recente e ainda atual; não usa um candidato reconstruído a partir de
um texto encontrado no documento. Toda a substituição entra em um lote ordenado.
Um envio parcial nunca é repetido. Nenhum Enter é simulado para colar mensagens.

No caminho web sem leitura do documento, a autorização é a sequência de entrada
acompanhada. Não existe prova integral do documento se o próprio editor reescrever
texto sem um evento de entrada/foco observável. Nesse caso o status é **Enviado**,
e não confirmação da formatação ou do documento inteiro. `{{cursor}}` requer
leitura verificável nessa rota; no Word ele é posicionado pelo intervalo nativo.

Word verifica literalmente o trecho e a janela antes de substituir. Se uma
chamada pode ter chegado ao Word mas sua resposta não veio, não há fallback para
Ctrl+V nem reenvio automático. Clipboard novo do usuário não é restaurado por uma
operação antiga. O conector não registra textos de documentos em arquivos de QA.

A rota antiga de seleção+cópia permanece como alternativa em controles com
capacidades diferentes, com comparação literal e cancelamento seguro. Não é
mais a dependência principal de Teams/navegadores.

## Validação

`tests/test_fast_expansion.py` cobre consulta repetida sem reler corpos, edições,
renomeação, exclusão/desfazer, alteração por outra conexão, rollback, atalhos
Unicode e aquecimento. As regressões transacionais verificam digitação/foco
concorrentes, clipboard, colagem única, ACK atrasado e posicionamento do cursor.

`packaging/smoke_accessibility.py` compila/exercita o worker em Windows real, em
uma janela WinForms descartável com Unicode, múltiplas ocorrências do atalho e
várias linhas. Confere seleção exata, movimentação do caret e rejeição de seleção
obsoleta, e registra tempos de consultas aquecidas. Não utiliza documentos reais.

`tests/test_native_insertions.py` verifica expansão sem seleção/cópia, foco,
revisão, candidato obsoleto, envio parcial, scan codes, passagem de conteúdo
formatado/cursor ao Word e ausência de reenvio em resultado incerto.
`tests/test_word_context.py` cobre cancelamento antes do envio e timeout após envio.

`packaging/smoke_web_expansion.py` usa o hook e o motor completos em Chrome externo,
com perfil descartável, `contenteditable` e iframe em `designMode`. Digita o atalho
com eventos reais do Windows; o editor bloqueia Shift+Left e produz cópia incorreta.
Confere uma colagem, zero cópias, fonte/cor/realce, Unicode e cancelamento quando o
usuário continua digitando. Não fabrica candidato nem substitui `is_current`.

`packaging/smoke_word_bridge.py` compila o conector STA, lê token, HTML e RTF reais
em outro processo, verifica cores/realce/fonte e exercita o contrato do modelo de
objetos com um documento sintético. Esse teste **não abre Microsoft Word** e não
comprova fidelidade visual numa instalação real do Office. É uma fronteira de
validação explícita; não deve ser anunciado como teste do Word ou Teams autenticados.

Os tempos máximos de proteção não são pausas impostas a toda expansão. Não há
promessa de um percentual de ganho sem comparar em hardware e aplicativos iguais.
Word/Teams continuam dependendo do provedor de acessibilidade e dos formatos
aceitos pelas versões instaladas; o smoke WinForms não equivale a testar o Office.

Referências técnicas: [UIA TextPattern](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/ui-automation-textpattern-overview),
[desempenho de TextRange](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-understandingperformanceissues),
[UIA e threads](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/ui-automation-threading-issues).

API Word: [modelo nativo](https://learn.microsoft.com/en-us/windows/win32/api/oleacc/nf-oleacc-accessibleobjectfromwindow), [formatação original](https://learn.microsoft.com/en-us/office/vba/api/word.wdrecoverytype).
