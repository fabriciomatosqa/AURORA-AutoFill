# AURORA AutoFill

**Expansão inteligente de textos • Mais tempo para você**  
Desenvolvido por Fabricio Matos

Expansor de textos desktop para Windows e Linux, criado em Python/PySide6. Organize comandos em pastas, escreva um atalho como `/resposta` e insira o texto em outros aplicativos. Os comandos, a formatação e as preferências ficam neste computador; a expansão não exige conta ou conexão com a internet.

## Retomada da base aprovada em 19/10/2026

Esta linha de desenvolvimento parte **exclusivamente** do commit funcional
[`1e451261ddf2a3fc0f060aaefe42dfaf328b77ae`](https://github.com/fabriciomatosqa/AURORA-AutoFill/tree/1e451261ddf2a3fc0f060aaefe42dfaf328b77ae)
(AURORA AutoFill **v0.6.1-191026**, [compilação aprovada #39292588074](https://github.com/fabriciomatosqa/AURORA-AutoFill/actions/runs/39292588074)).
Não substitua essa base pelo código antigo v0.5.x da `main` de outubro; ela não possui o mesmo atualizador, backups, recursos de expansão, controles de preferências e instaladores MSI.

### Exemplos iniciais: Conheça o AURORA

Somente quando não há banco de dados anterior, o aplicativo cria a pasta **Conheça o AURORA** com quatro comandos editáveis:

| Atalho | Apresentação |
| --- | --- |
| `/bemvindo` | Mensagem de boas-vindas e produtividade |
| `/tutorial` | Como criar atalhos e organizar textos em pastas |
| `/datahora` | Data/hora automáticas usando `{{data}}`, `{{hora}}` e `{{data_hora}}` |
| `/obrigado` | Agradecimento e motivação |

Os exemplos antigos `/ola`, `/agora`, `/chamado`, `/resposta` e `/colar` **não são mais cadastrados automaticamente em instalações novas**. O uso de `/ola` no tutorial é hipotético: o usuário poderá criar esse comando se desejar. Os quatro textos mantêm ênfase visual quando o programa de destino aceita HTML; a expansão em texto simples continua compatível.

Em instalações existentes, **nenhum comando pessoal é excluído nem substituído**. Os exemplos nunca são recriados após exclusão, restauração de backup ou atualização. Para testar o comportamento de primeira instalação, utilize um perfil temporário isolado; não apague dados pessoais.

### Pasta exclusiva de dados AuroraAutoFill

O AURORA AutoFill utiliza **somente** a pasta oficial abaixo, criando-a automaticamente quando necessário:

- Windows: `%APPDATA%\\AuroraAutoFill`
- Linux: `~/.local/share/AuroraAutoFill` (ou `$XDG_DATA_HOME/AuroraAutoFill`)

Nela ficam `snippets.sqlite3`, `settings.json`, backups e os demais dados do perfil. O aplicativo **não busca, importa, renomeia, move nem exclui** o antigo diretório `AutoFillStudio`. A pasta antiga permanece intocada, se existir.

**Atenção ao testar:** se seus comandos estão apenas no diretório antigo, eles **não aparecem automaticamente** na nova instalação. Exporte ou faça backup dos seus dados antes de trocar de instalação e importe ou restaure no AURORA quando desejar. Se a pasta nova não contiver banco de dados, serão criados os quatro exemplos da pasta **Conheça o AURORA**.

Os formatos de backup continuam compatíveis, incluindo o JSON legado `AutoFillStudioBackup`. Remover a migração entre *pastas* não altera os recursos de importar e restaurar backups.

### Nova marca transparente

A logo triangular transparente foi aplicada ao **cabeçalho, ícone da janela, bandeja, executável Windows, instalador Inno Setup, pacote MSI e aplicativo Linux**. Os arquivos PNG e ICO são derivados de uma versão otimizada da imagem enviada, com transparência RGBA. O GitHub Actions regenera os ícones antes da compilação e usa, no instalador, o mesmo ícone do executável validado.

Para compilar manualmente, prepare os ícones primeiro com `python -m pip install pillow` e `python scripts/build_branding.py`. O conteúdo do banco não muda ao atualizar a identidade visual.

## Ajustes de interface, Teams e rapidez dos atalhos

- **Botão Inserir imagem:** o pictograma antigo foi substituído pelo ícone SVG de fotografia, com traço arredondado, cor e tamanho idênticos aos demais controles do AURORA.
- **Teams e outros mensageiros:** a opção de converter toda a mensagem em uma figura foi **removida**. Em **Copiar para outro aplicativo**, aparecem as partes na ordem original (texto 1, imagem 1, texto 2 etc.), com **Copiar próxima parte**. Cada parte vai ao clipboard no formato correspondente: texto editável ou PNG/bitmap nativo. Cole cada parte com Ctrl+V e aguarde a imagem aparecer antes de prosseguir.
- **Atalho automático:** em destinos com suporte a HTML rico, o atalho preserva texto e imagens (como no Word). Em editores que só aceitam texto, apenas palavras editáveis são coladas, sem marcadores artificiais de imagem. O Teams pode exigir anexos separados; não há garantia de inserção automática de múltiplos prints em um único Ctrl+V.
- **Desempenho:** a expansão usa uma **consulta indexada pelo atalho** no SQLite em vez de carregar todos os comandos e suas imagens; também faz menos consultas redundantes a UI Automation e aquece seu serviço em segundo plano para reduzir a latência do primeiro uso. O pequeno tempo de estabilização de tecla caiu de 75 para **45 ms**, mas o tempo total real ainda depende da resposta do editor de destino. Todas as validações de contexto, texto e seleção para evitar exclusões indevidas continuam obrigatórias.

## Imagens e prints dentro dos comandos

O cabeçalho usa a marca AURORA com **108 × 108 pixels**, mantendo o banner original.

No editor de comandos, o botão **🖼 Inserir imagem** permite escolher uma foto ou um print (PNG, JPG, WebP ou BMP). Também é possível copiar uma captura de tela e colá-la com **Ctrl+V** diretamente entre os parágrafos.

- As imagens são convertidas em PNG, dimensionadas para facilitar a visualização e **incorporadas ao próprio HTML do comando** (`rich_content`) em vez de depender de links ou pastas externas.
- **Os backups completos e a exportação JSON preservam as imagens**, porque elas permanecem junto com os dados do comando.
- Por segurança e desempenho, cada imagem incorporada fica limitada a **2 MB**, cada comando a **12 imagens**, **10 MB** e **16 milhões de pixels decodificados** no conjunto. As dimensões são verificadas antes da decodificação. Novas inserções são reduzidas a até 1400 pixels por lado.
- A pré-visualização e a **área de testes** recebem texto formatado, imagens intercaladas e variáveis, incluindo `{{cursor}}`. A substituição na área de testes usa o intervalo exato do atalho, diretamente no editor.
- **Conteúdo misto:** o clipboard oferece HTML com figuras incorporadas para editores ricos, além de texto simples editável. Os dados salvos e os backups continuam com as imagens reais e sua posição.
- **Imagem isolada:** PNG e bitmap nativo, além do HTML, permitem colar um print como imagem independente. No Windows, os testes verificam CF_HTML e DIB/DIBV5 em outro processo.
- **Fluxo por partes:** no menu **Copiar para outro aplicativo**, escolha **Copiar próxima parte**, cole no Teams com Ctrl+V e repita. Também é possível escolher diretamente cada trecho ou imagem por sua posição. As cópias explícitas não são desfeitas pelo temporizador de restauração do clipboard.
- **Som em navegadores:** o áudio sinaliza que o AURORA acionou a colagem, não que o Teams aceitou os anexos. Se um app rejeitar PNG nativo, use o seletor de anexos do próprio aplicativo.
- **Segurança:** não usamos cliques por coordenadas, não enviamos mensagens e não automatizamos uma sequência de anexos sem confirmação de foco e aceitação. A expansão global com imagens requer seleção de texto verificável; em Linux essa capacidade permanece limitada.
- **Preferências antigas:** a chave `images_as_single_picture` é ignorada, mesmo se estava ativada. Não há migração do SQLite, das imagens ou dos backups.

Os comandos anteriores continuam compatíveis e não precisam ser modificados. Imagens copiadas de páginas da internet que dependam de URLs externas não são importadas automaticamente; salve a imagem localmente ou use uma captura para evitar referências quebradas.

O SQLite, `rich_content`, o texto alternativo já salvo (`[Imagem]`), JSON e ZIP de backup mantêm seus formatos. A conversão para os novos avisos ocorre apenas na preparação da expansão. Consulte o [diagnóstico, evidências e roteiro de validação](docs/expansao-imagens.md).

## Instalar e atualizar

Baixe os instaladores na página oficial de [GitHub Releases](https://github.com/fabriciomatosqa/AURORA-AutoFill/releases). **Durante o desenvolvimento, os lançamentos marcados como Pre-release são versões de teste e também aparecem no atualizador do aplicativo.**

**Receber versões de teste** vem ativado nas compilações de desenvolvimento. Para acompanhar somente versões estáveis, desmarque essa opção nas configurações; sua escolha fica salva.

- **Windows (.exe):** baixe `AURORA-AutoFill-v<versão>-Windows-Setup.exe` (Inno Setup, sem privilégios de administrador). É o formato atual e permite atualização automática pelo AURORA.
- **Windows (.msi):** baixe `AURORA-AutoFill-v<versão>-Windows-x64.msi` (WiX Toolset, Windows x64). O MSI usa a **mesma compilação PyInstaller** e é publicado junto com o EXE, com SHA-256 no manifesto Windows. Instala em `%LOCALAPPDATA%\\Programs\\AURORA AutoFill MSI` (sem exigir administrador), separado do Inno Setup, com registro de desinstalação e atalho no menu Iniciar. **Prefira somente um formato instalado por vez**: antes de trocar o EXE pelo MSI, desinstale o programa antigo após fazer backup. Os dados ficam em `%APPDATA%\\AuroraAutoFill` e não são removidos com a desinstalação.
- **Atualizações da instalação MSI:** a tela de atualizações abre o GitHub Releases para baixar o **próximo MSI**; ela não executa o instalador EXE/Inno. A automação de atualização silenciosa existente continua exclusiva da instalação EXE. Para instalar/atualizar via linha de comando: `msiexec /i AURORA-AutoFill-vVERSAO-Windows-x64.msi /qn /norestart`.
- **Ubuntu 24.04 amd64:** baixe o `.deb` e abra no gerenciador de pacotes, ou use `sudo apt install ./arquivo.deb`. Há também um `.tar.gz` portátil.

**Primeira migração da v0.6.0:** é necessário baixar e instalar esta nova compilação uma vez. O atualizador antigo procurava exclusivamente lançamentos estáveis e não consegue descobrir versões de teste. Depois dessa migração, use **⚙ Configurações → Verificar atualizações agora**; as próximas compilações poderão ser baixadas pelo programa.

### Como funciona a atualização pelo aplicativo

1. Ao iniciar, o AURORA consulta os lançamentos oficiais do repositório `fabriciomatosqa/AURORA-AutoFill`, se a opção de avisar estiver habilitada. Também é possível verificar manualmente nas configurações.
2. Compara a versão instalada com as publicadas, incluindo versões de teste com data como `0.6.1-161026` (16/10/2026). As datas são comparadas pelo calendário, inclusive na virada de mês e ano. Rascunhos e versões antigas não são oferecidos. O instalador precisa ser compatível com o sistema.
3. Oferece **Atualizar agora**. Esse clique autoriza o download, a verificação, o backup e a instalação. Mostra o progresso com opção de cancelar; a consulta e o download ocorrem em segundo plano.
4. Confere a integridade SHA256 e cria um backup completo **antes** de iniciar a instalação. Se o backup ou a verificação falhar, a instalação não é iniciada e o aplicativo continua aberto. Se houver edição não salva no editor, o aplicativo permite cancelar para protegê-la.
5. No Windows, fecha o AURORA, atualiza em segundo plano sem o assistente de “Avançar” e reabre automaticamente. A primeira instalação manual continua com o assistente normal. A cópia anterior ainda pode pedir a confirmação antiga de instalação ao receber esta mudança; nessa transição, o instalador mostra apenas o progresso e segue sozinho. As seguintes usam o fluxo de um clique e a instalação totalmente silenciosa.
6. No Linux, abre o `.deb` no gerenciador de pacotes; a confirmação e eventuais permissões são solicitadas pelo sistema. Se não houver gerenciador associado, a atualização pode ser instalada manualmente pela Release.

Nenhum comando ou conteúdo pessoal é enviado ao GitHub. A rede é usada para consultar lançamentos e baixar o instalador escolhido. SHA256 verifica a integridade em relação aos arquivos publicados; o instalador ainda não possui assinatura de código.

## Aparência: Claro, Escuro e Seguir o sistema

Em **Configurações → Aparência → Tema do aplicativo**, escolha **Claro**, **Escuro** ou **Seguir o sistema**. A troca é imediata, sem reiniciar, e fica salva em `settings.json`. Instalações novas começam em **Seguir o sistema**; perfis existentes e preferências/backups antigos sem o campo `theme` conservam o visual **Escuro**. O padrão da instalação nova é gravado na primeira abertura, para permanecer igual nas aberturas seguintes.

**Seguir o sistema** consulta `QStyleHints.colorScheme()` e acompanha `colorSchemeChanged` do Qt tanto no Windows quanto no Linux. Quando a plataforma ou o ambiente gráfico não informa a aparência, o fallback é **Escuro**. Claro e Escuro ignoram mudanças do sistema. No Linux, a detecção depende da integração do Qt com o ambiente gráfico utilizado.

O tema claro cobre os painéis, editor, ferramentas, SVGs, menus, configurações, avisos e diálogos Qt. A troca atua nos estilos e na paleta da interface: **não reescreve o HTML nem as cores, realces, fontes ou imagens dos comandos**. Conteúdo pessoal com cores explícitas continua com essas cores em ambos os temas.

O tema escuro mantém `assets/aurora_banner.jpg`. O claro usa a paisagem diurna limpa `assets/aurora_banner_day.png`, sem logo ou textos incorporados. Os dois temas usam a mesma logo transparente, título e subtítulo desenhados pela interface, com posição e tamanho idênticos. O gradiente do cabeçalho mantém a leitura da marca e dos botões sobre ambas as paisagens. O cabeçalho conserva 168 pixels de altura, os botões e a proporção da paisagem. Acima de 1320 pixels de largura, bordas da paisagem são refletidas sem ampliar excessivamente ou repetir a assinatura. A verificação dos bundles exige os dois banners, com hashes iguais aos recursos de origem.

Os testes automatizados cobrem seleção e persistência, migração de perfis, sinal nativo do Qt, fallback, banner em 1060/1320/1920/2560 pixels, diálogos e preservação do conteúdo e da seleção. A entrega de eventos reais de aparência depende do desktop; conferir manualmente a mudança de tema nas configurações do Windows e do ambiente Linux utilizado. Diálogos de arquivo nativos seguem a aparência do próprio sistema operacional.

## Recursos

- **Pastas e ordenação:** arraste comandos para reorganizar; a ordem permanece salva ao reiniciar. Excluir uma pasta transfere seus comandos para outra pasta.
- **Desfazer por 10 segundos:** ao excluir um comando ou uma pasta, use o aviso no rodapé para recuperar a operação.
- **Editor e prévia 60/40:** edição com formatação e visualização do texto final.
- **Variáveis:** data, hora, área de transferência e marcador `{{cursor}}`.
- **Gota de confirmação:** gravação Water Droplet 2, de floraphonic, ao salvar e expandir comandos. Liga/desliga e volume nas configurações; créditos em `assets/AUDIO-LICENSE.txt`.
- **Central de configurações:** áudio, início com Windows, opção **Iniciar minimizado** na bandeja do sistema, backups e atualizações. O botão de configurações usa uma engrenagem SVG simétrica de seis dentes.
- **Visual Aurora:** azul noite e ciano, menus arredondados e configurações integradas ao tema.
- **Uma instância por perfil:** impede que duas cópias do programa processem o mesmo atalho simultaneamente. Se já estiver aberto, acesse o ícone próximo ao relógio.

**Formulários dinâmicos não foram implementados** e continuam aguardando avaliação.

## Proteger e recuperar os dados

**Exportar JSON** inclui todas as pastas e todos os comandos, com formatação e ordem. **Importar JSON** acrescenta os dados ao banco atual; não apaga comandos existentes e ignora atalhos já cadastrados. Pastas vazias também são preservadas.

**Criar backup completo** salva um `.aurora-backup.zip` com o banco SQLite e as preferências. **Restaurar backup** substitui os dados atuais pelos do arquivo selecionado, após confirmação. Uma cópia de segurança é criada antes de restaurar. A estrutura do arquivo é validada antes da substituição.

Os arquivos ficam em:

| Dados | Windows | Linux |
| --- | --- | --- |
| Pasta de dados | `%APPDATA%\AuroraAutoFill` | `~/.local/share/AuroraAutoFill` |
| Banco | `snippets.sqlite3` | `snippets.sqlite3` |
| Preferências | `settings.json` | `settings.json` |
| Backups completos | Subpasta `backups` | Subpasta `backups` |

Backups manuais não são apagados automaticamente. Backups automáticos pré-atualização mantêm as últimas cinco cópias. O botão **Abrir backups** abre a pasta de recuperação.

## Compilações e histórico de versões

Cada push em `dev/correcao-expansao-windows` ou `main` executa [os testes e a compilação Windows EXE/MSI e Linux](https://github.com/fabriciomatosqa/AURORA-AutoFill/actions/workflows/build-installers.yml). Somente depois de ambos os sistemas passarem, os instaladores e os checksums são publicados juntos em uma **Pre-release**. A versão usa `BASE-DDMMAA`, por exemplo `0.6.1-161026`, com a data no horário de Brasília. Uma segunda atualização no mesmo dia recebe `.2`, a terceira `.3`, preservando as publicações anteriores. Repetir uma compilação do mesmo commit reutiliza sua versão.

**Transição da v0.6.1-dev.22.1:** o atualizador já instalado usa SemVer e considera um sufixo numérico anterior a `dev`. Para permitir o teste remoto, cada lançamento com data também publica uma referência de compatibilidade `BASE-update.AAAAMMDD` (e a mesma revisão, quando houver). Ela contém cópias dos mesmos instaladores, com nomes e manifestos SHA256 esperados pelo cliente antigo. Por isso, a primeira confirmação no aplicativo antigo poderá mencionar `0.6.1-update.20261016`; após instalar, a janela, o rodapé e o instalador mostram `0.6.1-161026`. O novo atualizador reconhece ambos como a mesma versão e não propõe reinstalação. Ambos os lançamentos continuam sendo de teste.

Os artifacts de diagnóstico do Actions expiram em 30 dias. Os instaladores publicados em Releases permanecem disponíveis para recuperação; o workflow não apaga Releases estáveis nem de teste.

A base da próxima versão fica apenas em `app/version.py`. `packaging/build_version.py` grava os metadados da compilação antes dos testes e do empacotamento; aplicativo, nome dos instaladores e tag principal usam a mesma versão com data. O Windows recebe também uma versão numérica; o DEB usa `~update.AAAAMMDD` para manter a ordem cronológica, superar os pacotes `~dev` e ficar abaixo da futura versão estável. Os metadados de versão não alteram a pasta de dados nem o identificador do aplicativo.

Uma versão estável exige uma tag intencional `vX.Y.Z`, correspondente à base em `app/version.py`, e ambos os builds aprovados. Depois de publicar uma estável, aumente a base para a próxima versão antes de continuar os testes. Preserve pelo menos as últimas três Releases estáveis.

## Desenvolvimento e testes

Python 3.11 ou mais novo:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python main.py
```

Para executar os testes de interface sem monitor, defina `QT_QPA_PLATFORM=offscreen`. Os testes usam perfis temporários e simulações de teclado, sem enviar comandos a outros aplicativos.

O GitHub Actions também verifica os recursos empacotados, inicia os executáveis compilados em perfis temporários e confirma a preservação dos dados antes de publicar os instaladores. Depois da publicação, o atualizador novo e o código exato do atualizador da `0.6.1-dev.22.1` consultam e baixam os instaladores Windows/Linux, verificando o SHA256 sem executá-los. Para converter novamente a gravação fornecida, use `python tools/import_feedback.py caminho/do/audio.mp3`; o gerador antigo é apenas uma alternativa sintética.

## Limitações e validação manual

- A colagem e o posicionamento do cursor dependem do aplicativo de destino. Valide com as versões de Word, Bloco de Notas, navegadores e Teams utilizadas no seu computador.
- Linux exige X11/Xorg para atalhos globais; Wayland pode impedir a captura. O DEB distribuído é voltado a Ubuntu 24.04 amd64.
- **Iniciar com Windows** usa a chave `Run` do usuário atual. Ao marcar **Iniciar minimizado** ao lado, o Windows executa o aplicativo com `--minimized`: os atalhos ficam ativos na bandeja do sistema, sem abrir a janela. A abertura manual pelo atalho continua normal. É necessário haver suporte à bandeja do sistema; a posição do ícone, inclusive a área de ícones ocultos, é definida pelo próprio Windows.
- O instalador Windows não está assinado digitalmente; o Windows pode exibir o aviso do SmartScreen.
- A fonte em desenvolvimento abre a página da Release para instalar o pacote. A substituição da própria cópia está disponível nos aplicativos empacotados.


### Reconhecimento e preenchimento otimizados

O reconhecimento usa a mesma comparação Unicode do cadastro e da recuperação:
`/AÇÃO` encontra `/ação`, inclusive em perfis com muitos modelos. Os metadados dos
atalhos ficam separados dos corpos e imagens. Modelos utilizados recentemente
têm cache limitado, invalidado por edição, exclusão, importação e mudanças do banco.
Data, hora e clipboard continuam sendo resolvidos novamente em cada expansão.

No Windows, o processo auxiliar de acessibilidade compila o seu motor C# uma vez
na inicialização. Ele continua isolado, com prazo máximo para resposta, sem gravar
texto dos documentos. Quando a seleção já foi comprovada pelo worker, a colagem
usa essa prova imediatamente, sem uma consulta redundante ao documento inteiro.
Um ACK de seleção ainda pendente nunca autoriza colar sozinho.

Detalhes, verificações e limites: [motor de preenchimento](docs/motor-preenchimento.md).
