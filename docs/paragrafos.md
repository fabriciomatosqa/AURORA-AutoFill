# Formatação de parágrafos

A faixa de formatação mantém as três linhas do grupo Fonte com a mesma largura.
O grupo Parágrafo fica ao lado, separado por uma linha vertical. Inserir imagem
e Inserir comando dinâmico ficam na linha seguinte. A lista de fontes continua
com a largura e a quantidade de itens visíveis anteriores.

As ferramentas atuam nos parágrafos selecionados ou no parágrafo do cursor:

- Alinhamento à esquerda, centralizado, à direita e justificado.
- Marcadores redondos, vazados e quadrados; numeração decimal, alfabética e romana;
  lista de vários níveis com sequência 1 → a → i, até nove níveis.
- Aumentar/diminuir recuo; Tab/Shift+Tab no início de um item altera seu nível.
- Espaçamento entre linhas e antes/depois dos parágrafos.
- Sombreamento e bordas, com cor e espessura selecionáveis.
- Classificação de parágrafos por texto ou número, em ordem crescente/decrescente,
  com opção de manter a primeira linha como cabeçalho.
- Mostrar/ocultar espaços, tabulações e marcas de parágrafo, sem inserir esses
  símbolos no texto salvo ou copiado.

O botão no canto do grupo abre **Parágrafo**. A primeira aba permite configurar
recuos à esquerda/direita, primeira linha ou deslocamento, medidas em cm,
espaçamento em pt, entrelinhas simples/1,5/duplo/múltiplos/mínimo/exato,
nível do tópico e espaçamento contextual. **Tabulação** permite posições,
alinhamento à esquerda/centro/direita/decimal e preenchimento pontilhado,
tracejado ou contínuo. **Definir como padrão** grava as opções para novos comandos;
os comandos existentes mantêm sua formatação. Cancelar não altera o documento;
o botão de definir padrão é uma gravação explícita independente do OK.

A aba **Quebras de linha e de página** preserva controle de linhas órfãs/viúvas,
manter com o próximo, manter linhas juntas, quebra antes, exceções de numeração
e hifenização, além de opções de disposição em caixas de texto. O Aurora usa
uma visualização contínua, sem páginas ou caixas de texto: essas opções são
exportadas para destinos compatíveis. O nível do tópico não troca a fonte do
usuário por um estilo de título. Recolhimento é uma opção para a visualização
de estrutura do destino, sem esconder o conteúdo no editor Aurora.

Atalhos do editor: Ctrl+L/E/R/J para alinhamentos, Ctrl+M e Ctrl+Shift+M para
recuos, Ctrl+1/2/5 para entrelinhas simples/duplo/1,5 e Ctrl+Shift+8 para marcas.
Esses atalhos não são globais; funcionam dentro do campo de mensagem.

## Persistência e colagem

As propriedades nativas ficam no HTML do documento. Um metadado versionado
`aurora-paragraphs` armazena somente as opções adicionais e medidas exatas que o
exportador Qt arredondaria. Ele não duplica o texto, aceita apenas propriedades
conhecidas e possui limites de tamanho, quantidade e valores. Backups continuam
usando os campos HTML e preferências já existentes.

Na expansão de texto, HTML interoperável preserva parágrafos, listas e estilos.
No Windows, a rota Office também oferece RTF com listas nativas, medidas em
twips, tabulações e controles de paginação. Documentos com imagens permanecem em
HTML, preservando imagens e tabelas. As rotas existentes de anexos separados do
Teams continuam obedecendo às capacidades do destino. Campos de texto simples
recebem texto simples; o editor de destino decide quais estilos HTML/RTF aceita.

Os testes cobrem salvar/reabrir, seleção, desfazer, listas, classificação,
precisão de medidas, metadados e colagem. `packaging/smoke_paragraphs.py` usa
RichEdit real do Windows para ler RTF sintético, verificando texto, alinhamento,
recuo, negrito e listas. Isso não representa um teste com Word ou Teams instalados.
