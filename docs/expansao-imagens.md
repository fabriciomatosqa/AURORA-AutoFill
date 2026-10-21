# Expansão de textos com imagens — diagnóstico e validação

Base: main `b5aebf2`, tag `v0.6.1-191026.4`. Trabalho em `fix/mixed-image-expansion`.
Nenhum arquivo de `sources/`, dado pessoal, formato de backup ou esquema SQLite foi alterado.

## Causas reproduzíveis

1. `AuroraImageEditor.insert_image` armazena PNG Base64 no `src` de `<img>` em `rich_content`. O editor mantém U+FFFC como posição da imagem em `toPlainText`; `plain_text_fallback` grava `[Imagem]` na coluna `content`. Persistência, JSON e ZIP já preservavam a figura em HTML.
2. `_submit_expansion` publicava apenas `text/plain` e `text/html`. Nenhum PNG ou bitmap acompanhava a figura. Quando o destino consumia `text/plain`, recebia literalmente o marcador salvo. Uma imagem em uma string HTML não é um arquivo/imagem nativa do clipboard.
3. A área de testes usava `QPlainTextEdit`: reproduzia esse problema dentro do próprio AURORA, independentemente de qualquer restrição externa.
4. O editor priorizava `hasImage()` antes de HTML. Um clipboard com HTML misto e uma imagem alternativa podia perder os parágrafos na inserção no editor.
5. A confirmação comparava o resultado apenas ao texto com `[Imagem]`. Um editor rico que representasse imagens como U+FFFC não poderia confirmar corretamente a substituição nem posicionar `{{cursor}}` pelo documento real.
6. Sem snapshot verificável, a expansão recorria à seleção por teclas. Nas capturas de Teams/ChatGPT o atalho ficou junto ao conteúdo: isso comprova substituição incompleta, mas não identifica sozinho qual componente do editor ignorou ou perdeu a seleção. A correção com imagens exige leitura do atalho, seleção do intervalo e confirmação antes de enviar Ctrl+V; se a acessibilidade não fornece o intervalo, cancela. Não há reenvio após resultado incerto.
7. A clonagem anterior copiava somente buffers MIME. O formato Qt de imagem pode transportar um QImage como QVariant; agora a clonagem preserva também `imageData()`.

## Implementação

`clipboard_content.py` prepara, sem alterar os dados salvos, duas representações do mesmo conteúdo: HTML com imagens em ordem e texto simples editável, sem marcadores artificiais de imagem. Usa o texto do documento rico para acompanhar U+FFFC, variáveis, emojis e `{{cursor}}`. A data/hora da expansão é única para as representações.

Conteúdo misto não oferece um bitmap da primeira figura: isso permitiria que um destino descartasse o restante da mensagem ao escolher a representação de imagem. Somente uma imagem isolada oferece também `image/png` e `setImageData`. Qt faz a conversão nativa para CF_HTML e DIB/DIBV5; não mantemos uma implementação paralela de offsets CF_HTML nem fabricamos handles CF_BITMAP. PNG é um formato registrado no Windows; `image/png` é o MIME oferecido por Qt.

A área de testes usa `AuroraImageEditor`. O motor substitui o intervalo validado diretamente pelo Qt, sem injetar seleção e Ctrl+V no próprio processo. A confirmação aceita o documento rico ou a representação textual explícita, e não confunde confirmação de texto via acessibilidade com comprovação de que uma figura apareceu em um aplicativo externo.

O menu **Copiar para outro aplicativo** oferece cada trecho de texto e cada imagem como uma parte separada, na ordem original. A ação **Copiar próxima parte** avança pela sequência; o texto é enviado em text/plain editável e as imagens em PNG/bitmap nativo. A opção de converter toda a mensagem em uma figura foi removida. A cópia manual permanece no clipboard. Não automatizamos uma sequência texto–anexo–texto: não existe confirmação genérica de conclusão de upload, de foco ou de posição de um anexo nos destinos. Não usamos coordenadas, não enviamos mensagens, não contornamos políticas do destino e não fazemos novas tentativas depois de uma colagem incerta.

Mantivemos revisão do teclado, contexto/foco, identidade de campo, limites de tempo de consulta, token/lease e proteção contra sobrescrever uma nova cópia. Sem contador nativo Windows, uma revisão local alimentada por `QClipboard.dataChanged` detecta mudança durante a preparação. A janela de disponibilidade de 1450 ms já existente é mantida também para conteúdo com imagens: confirmar o texto não confirma que um leitor externo terminou de pedir seus dados. É uma disponibilidade limitada, não um recibo de colagem. A clonagem preserva os formatos expostos por Qt; objetos OLE privados de aplicações não têm garantia de reconstrução completa.

Limites: até 12 imagens, 2 MiB por arquivo incorporado, 10 MiB de arquivos por comando, 16 milhões de pixels no total e até 8192 pixels por lado na leitura. Inserções são reduzidas a até 1400 pixels por lado. Cabeçalhos são inspecionados antes de decodificar arquivos/URIs; validar o conjunto impede que duas colagens individualmente válidas excedam os limites. Fontes externas, duplicadas, ausentes, sem aspas e imagens inválidas são tratadas. O documento Qt bloqueia carregamento de arquivos/URLs externos, inclusive ao abrir HTML legado/importado; dados inválidos permanecem editáveis, mas sem carregar suas imagens. A gravação/expansão recusa imagens inválidas.

## Arquivos

- `app/clipboard_content.py`: preparação de representações, PNG nativo e clonagem MIME.
- `app/inline_images.py`: prioridade do HTML, recursos em memória e limites antes da decodificação.
- `app/expansion.py`: estado do documento rico para confirmação/cursor.
- `app/ui.py`: área de testes, intervalo exato, cópia manual e controle do clipboard.
- `tests/test_mixed_clipboard.py`, `tests/engine_fixture.py`: documentos Qt reais e motor externo simulado.
- `packaging/smoke_clipboard.py`, `.github/workflows/build-installers.yml`: leitor Win32 em segundo processo, inserido na CI.
- `README.md`, este relatório e `.gitignore`: comportamento/limites e exclusão dos ambientes locais de testes.

## Evidências e seus limites

Validação local Windows: suíte completa, incluindo os testes existentes de atualização, instaladores, backups, contextos e seleção, mais 23 testes deste fluxo. A execução final e os resultados da compilação ficam associados ao commit do PR. O CI regenera os PNG/ICO a partir da marca existente antes dos testes; o mesmo preparo foi feito localmente, sem incluir novas imagens de marca no patch.

O smoke nativo Windows utiliza Qt com plataforma `windows`, disponibiliza exclusivamente dados sintéticos e lê os formatos via Win32 em outro processo. Confere offsets UTF-8 do CF_HTML (inclusive emoji e imagens), CF_UNICODETEXT, assinatura PNG e cabeçalho DIB/DIBV5; verifica que conteúdo misto não oferece um bitmap parcial. Restaura o clipboard se sua sequência ainda pertence ao teste. Esse teste passou localmente. A CI o executa novamente em seu runner.

| Destino/fluxo | Evidência disponível nesta mudança |
| --- | --- |
| Editor e área de testes AURORA | Widgets/documentos Qt reais: duas imagens intercaladas, texto formatado, emoji, variável, cursor e substituição exata |
| Clipboard Windows | Formatos nativos lidos por outro processo; não é teste de Word/Teams/ChatGPT |
| Destino somente texto | QPlainTextEdit real recebe os parágrafos editáveis, sem marcadores falsos de imagem |
| Motor externo | Simulações reproduzíveis de seleção, mudança de foco, destino ilegível, cópia concorrente e restauração |
| Persistência/JSON/ZIP | Reabertura do SQLite, duas imagens e round-trip integral sem migração de esquema |
| Word | Captura fornecida comprova a versão anterior; testar manualmente esta compilação |
| ChatGPT, Teams, aNotepad | Capturas fornecidas comprovam a falha anterior; aceitação da nova compilação ainda depende do teste manual abaixo |
| Linux | CI valida suíte, bundle, DEB e portátil. A expansão global com imagens é recusada quando não há seleção verificável; cópia manual e teste interno funcionam sem depender desse provedor |

## Roteiro manual da compilação candidata

1. Faça backup completo. Instale o EXE candidato do PR (ou teste MSI separadamente); confira a versão no rodapé e registre navegador/app e versão. Mantenha um texto, depois um print, outro parágrafo, uma segunda imagem diferente e um parágrafo final no mesmo comando `/imgteste`. Salve e reabra o AURORA.
2. Na área de testes, escreva `Antes 😀 ` e digite `/imgteste`. Confirme que o atalho desaparece, os vizinhos permanecem, as duas imagens aparecem na ordem e o texto continua após elas. Repita com negrito, quebras de linha, `{{data}}`, `{{clipboard}}` e `{{cursor}}`.
3. No Word, em um documento vazio, repita a expansão e confira visualmente as duas figuras e a formatação. Não basta ver os parágrafos. Repita com uma imagem isolada.
4. Em rascunhos vazios do ChatGPT e Teams, repita sem enviar. Registre separadamente: atalho removido, texto completo, imagens no corpo, imagens anexadas ou apenas aviso. Se o intervalo não puder ser verificado, o comportamento esperado é cancelar e preservar o atalho.
5. Para testar o fallback, no AURORA abra o comando, escolha **Copiar texto sem imagens**, volte ao rascunho e cole. Depois use **Copiar imagem 1** e cole no mesmo rascunho, aguardando a miniatura/anexo aparecer; repita para a segunda imagem. Não há garantia de imagem intercalada quando o destino usa anexos. Se PNG/bitmap também for rejeitado, use o seletor de anexos do próprio destino.
6. Repita em aNotepad/campo somente texto e num editor `contenteditable` que aceite imagens: somente texto deve manter as palavras editáveis e não adicionar avisos como se fossem parte da mensagem; o suporte a HTML do outro editor deve ser conferido visualmente. Um campo `<textarea>` não pode mostrar imagens.
7. Antes de expandir, copie um texto e uma imagem de teste. Depois de confirmar a expansão e aguardar a restauração, cole em um documento descartável para conferir o conteúdo anterior. Faça uma nova cópia durante uma tentativa e confirme que ela prevalece. Troque o foco antes da substituição e confirme que nenhum outro campo recebe texto. Não use dados sensíveis nesse ensaio.
8. Exporte JSON, faça backup ZIP e restaure em perfil descartável. Confirme texto e ambas as imagens. Para MSI, faça os ensaios de instalação/desinstalação em um perfil de teste.

Não publicar como compatibilidade externa comprovada antes desses testes. O PR permite validar EXE, MSI e Linux sem executar o job de release; main, tags e release não são alteradas durante essa validação. Versão e arquivos finais são gerados pelo fluxo existente, sem atribuir manualmente uma tag ainda não publicada.

## Referências técnicas

- [Qt QMimeData e conversão de formatos Windows](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QMimeData.html).
- [Qt QClipboard](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QClipboard.html).
- [Microsoft Clipboard Formats: DIB, DIBV5 e conversões](https://learn.microsoft.com/en-us/windows/win32/dataxchg/clipboard-formats).
