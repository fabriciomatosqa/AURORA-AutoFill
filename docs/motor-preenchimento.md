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

## Contratos preservados

Janela, campo, revisão de teclado, identidade do documento e propriedade do
clipboard são revalidados. Texto que muda ou seleção inesperada cancela a
operação. Nenhum retry de leitura reenvia Ctrl+V. O clipboard copiado pelo usuário
posteriormente não pode ser substituído por restauração antiga. Campos de senha
não são lidos. Dados transitam em pipes anônimos; não são logs ou arquivos de QA.

O ACK não é uma confirmação. O fallback de seleção + cópia só permite colar
quando a cópia corresponde exatamente ao atalho, nos destinos suportados.
HTML/RTF, imagens, quebras de linha e `{{cursor}}` mantêm os caminhos existentes.

## Validação

`tests/test_fast_expansion.py` cobre consulta repetida sem reler corpos, edições,
renomeação, exclusão/desfazer, alteração por outra conexão, rollback, atalhos
Unicode e aquecimento. As regressões transacionais verificam digitação/foco
concorrentes, clipboard, colagem única, ACK atrasado e posicionamento do cursor.

`packaging/smoke_accessibility.py` compila/exercita o worker em Windows real, em
uma janela WinForms descartável com Unicode, múltiplas ocorrências do atalho e
várias linhas. Confere seleção exata, movimentação do caret e rejeição de seleção
obsoleta, e registra tempos de consultas aquecidas. Não utiliza documentos reais.

Os tempos máximos de proteção não são pausas impostas a toda expansão. Não há
promessa de um percentual de ganho sem comparar em hardware e aplicativos iguais.
Word/Teams continuam dependendo do provedor de acessibilidade e dos formatos
aceitos pelas versões instaladas; o smoke WinForms não equivale a testar o Office.

Referências técnicas: [UIA TextPattern](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/ui-automation-textpattern-overview),
[desempenho de TextRange](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-understandingperformanceissues),
[UIA e threads](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/ui-automation-threading-issues).
