# AURORA AutoFill

**Expansão inteligente de textos · Mais tempo para você**  
Aplicativo desktop de produtividade para Windows e Linux, desenvolvido por Fabricio Matos. Código em Python e PySide6.

Digite um atalho como `/resposta` em um campo de texto para solicitar a inserção de um modelo salvo. Os textos, pastas, preferências e métricas ficam no seu computador, sem conta ou internet obrigatória para os recursos locais.

> **Estado do projeto (29/10/2026):** a base consolidada inclui formatação rica, imagens, menus de parágrafo, emojis Fluent, temas claro/escuro, backups, atualizações online e compatibilidade aprimorada com Word, Teams e editores Web. O suporte Wayland e as automações avançadas são **experimentais**, com limitações documentadas.

## Instalar e atualizar

Baixe somente os arquivos publicados na página oficial: [GitHub Releases](https://github.com/fabriciomatosqa/AURORA-AutoFill/releases). O aplicativo consulta novas versões ao iniciar e, quando habilitado, periodicamente, sem enviar seus modelos ao GitHub.

| Plataforma | Instalação | Atualização |
| --- | --- | --- |
| Windows (recomendado) | `...-Windows-Setup.exe` (Inno Setup por usuário) | Download verificado, backup e instalador automático após confirmação |
| Windows MSI | `...-Windows-x64.msi` (WiX) | Atualização manual para outro MSI; não misture com o instalador EXE |
| Ubuntu/Linux amd64 | `...-Linux-amd64.deb` | Abre o gerenciador de pacotes; confirmação do sistema |
| Linux portátil | `.tar.gz` publicado na mesma release | Extração manual |

As versões de desenvolvimento podem ser **Pre-release**. Em **Configurações**, o usuário decide receber ou não versões de teste. Um manifesto SHA-256 protege a integridade do download, mas os instaladores Windows **não têm assinatura de código** nesta fase.

**Dados e caminhos:**

- Windows: `%APPDATA%\AuroraAutoFill`
- Linux: `~/.local/share/AuroraAutoFill` (respeita `XDG_DATA_HOME`)
- Arquivos: `snippets.sqlite3`, `settings.json`, subpasta `backups`.

Nenhuma atualização apaga ou recria seus comandos. O diretório legado `AutoFillStudio` não é importado automaticamente: utilize **Exportar / Importar** ou um backup, se necessário.

## Como utilizar

1. Clique em **+ Novo**.
2. Informe título, atalho único (ex.: `/chamado`) e pasta.
3. Edite o texto com formatação de fonte, parágrafo, listas, cores, imagens e emojis.
4. O conteúdo válido é salvo automaticamente no SQLite. A **Pré-visualização** é somente leitura.
5. Abra outro aplicativo e digite seu atalho. O AURORA verifica o contexto e tenta colar o resultado no editor.
6. Em **Configurações**, controle áudio, aparência, sugestões e atualização online.

As instalações novas recebem a pasta **Conheça o AURORA**, com exemplos `/bemvindo`, `/tutorial`, `/datahora` e `/obrigado`. Eles são criados somente na **primeira instalação sem banco anterior**. Apagar ou restaurar comandos não recria esses exemplos.

### Aparência, editor e clipboard

- Temas: **Claro**, **Escuro** ou **Seguir o sistema**. A faixa de paisagem usa banners correspondentes dia/noite com composição alinhada, mesmo logotipo e controles.
- Editor rico: fontes locais, negrito, itálico, sublinhado, riscado, cores, alinhamento, espaçamentos e estilos de parágrafo.
- Emojis: seletor com categorias, busca e ícones Fluent coloridos; o conteúdo inserido permanece Unicode editável.
- Imagens: PNG/JPG/WebP/BMP e prints colados. As figuras são incorporadas no HTML do comando, com limites de tamanho e quantidade, sem dependência de URL externa.
- Pré-visualização: espelho visual sem foco ou comandos de edição.
- Word e navegadores: usam HTML e formatos suportados pelo destino quando disponíveis; se a aplicação só aceita texto simples, o texto permanece editável. O Teams pode exigir anexos separados.
- Som de confirmação e volume próprios; som não garante que o aplicativo de destino aceitou uma imagem.
- O mecanismo de colagem não repete tentativas de envio em resultados incertos para evitar duplicações.

Consulte [expansão e imagens](docs/expansao-imagens.md), [motor de preenchimento](docs/motor-preenchimento.md) e [parágrafos](docs/paragrafos.md).

## Produtividade e modelos inteligentes

### Formulários interativos

Insira, no modelo, um campo de texto ou uma lista de opções:

```text
Olá {{campo:Nome}}!

O chamado {{campo:Número}} está com situação:
{{escolha:Situação|Aberto|Em andamento|Concluído}}.
```

Quando o comando é escolhido ou o atalho é digitado, uma janela solicita os valores com o **primeiro campo já em foco**. Campos repetidos aparecem separadamente, em ordem (Nome (1), Nome (2) etc.), podendo receber respostas diferentes. Os dados preenchidos **não são salvos no modelo**. Ao cancelar, o texto previamente digitado no destino não deve ser apagado.

Em Windows, após o formulário, o AURORA tenta restaurar e verificar o campo original antes de colar; se não puder provar o destino, **copia o resultado para Ctrl+V manual**. Linux usa o fluxo seguro de copiar quando não consegue verificar o campo externo.

### Pesquisa global e sugestões

- **Pesquisa global** no painel lateral ou **Ctrl+Shift+Espaço** em outros aplicativos, quando a captura de atalhos está disponível. Pesquise por nome, atalho ou palavras do conteúdo.
- Selecionar um modelo prepara a inserção. A colagem automática só é tentada no Windows quando a janela original pode ser confirmada; em situações incertas o comando fica no clipboard para Ctrl+V.
- **Sugestões enquanto digita**: opção voluntária em Configurações, **desligada por padrão**. Mostra até cinco atalhos após digitar `/` e outros dois caracteres. Use a pesquisa global para selecionar.
- A captura global de teclado não distingue com segurança todos os campos de senha, principalmente no Linux. Não habilite sugestões flutuantes em sessões compartilhadas ou durante edição de informações sensíveis.

### Datas e variáveis

| Variável | Efeito |
| --- | --- |
| `{{data}}`, `{{hora}}`, `{{data_hora}}` | Data e horário locais atuais |
| `{{clipboard}}`, `{{area_transferencia}}` | Conteúdo textual atual do clipboard |
| `{{cursor}}` | Solicita posicionamento do cursor ao concluir (depende do aplicativo) |
| `{{data:+7}}`, `{{data:-1}}` | Data deslocada em dias, até 10 anos |
| `{{data_formato:%Y-%m-%d}}` | Formato customizado de data suportado |
| `{{calculo:12*3}}` | Aritmética simples, sem avaliar código Python |

As variáveis são resolvidas em cada uso, não durante o salvamento. As variáveis desconhecidas continuam visíveis no texto e não causam execução arbitrária.

### Automações em etapas — experimental

```text
{{campo:Nome}}{{tab}}{{campo:Matrícula}}{{tab}}Ativo{{enter}}
```

Ações disponíveis: `{{tab}}`, `{{enter}}`, `{{espera:250}}`. São no máximo 20 etapas e 5 segundos de espera. **Uma janela pede confirmação** antes de executar. A execução automática por teclado é restrita a Windows e a janela original verificável; se o foco mudar, interrompe. Em Linux a alternativa é copiar o texto para colagem manual, sem pressionar teclas arbitrárias.

Não use automações em senhas, transferências financeiras, procedimentos irreversíveis nem formulários não testados. Confirme todos os valores antes de enviar.

### Estatísticas locais

Abra **Estatísticas** no painel esquerdo para consultar o total de comandos utilizados hoje, no mês, no ano e desde o começo, além das barras mensais e modelos mais usados.

- São incrementadas **somente expansões confirmadas** pelo mecanismo principal. Ações manuais ou inserções sem verificação podem não ser contabilizadas.
- Apenas IDs, atalhos e quantidades diárias são armazenados em `usage_daily` no SQLite. Nenhum conteúdo digitado em outros aplicativos, senha ou histórico de teclas é salvo como métrica.
- **Limpar estatísticas** apaga os contadores, sem excluir os modelos.
- Os backups completos incluem os contadores; exportar comandos em JSON não inclui métricas.

### Busca indexada

O SQLite usa **FTS5** com Unicode e remoção de diacríticos para buscas por início de palavras. Instalações sem FTS5 e buscas que não encontrem resultados recorrem à pesquisa `LIKE` anterior, preservando compatibilidade com trechos do meio das palavras. O índice se atualiza com inclusões, alterações e exclusões.

[Documentação detalhada da produtividade](docs/produtividade.md)

## Linux: X11 e GNOME Wayland

- **X11/Xorg:** o monitor pynput pode reconhecer atalhos globais.
- **GNOME Wayland:** o backend experimental usa `evdev` (leitura de dispositivos físicos) e `uinput` (teclado virtual). A sessão gráfica não oferece permissão automática para qualquer app capturar digitação global, por segurança.
- O aplicativo abre, edita, pesquisa e copia comandos mesmo sem a permissão de captura.
- Em **Configurações → Configurar atalhos no Linux Wayland**, há um assistente que explica o acesso e, após consentimento explícito, abre um terminal com os comandos necessários. O sistema pode pedir senha de administrador e **exigir novo login**.
- Essa autorização é poderosa: estar no grupo `input` concede acesso amplo a dispositivos de entrada. Não habilite em computadores públicos/compartilhados, não execute o AURORA como root e não conceda o acesso silenciosamente via instalador.
- **Ainda não existe expansão global de textos completamente sem permissões no GNOME Wayland.** Portais XDG convencionais não fornecem um fluxo geral de leitura de todas as sequências digitadas. A compatibilidade real depende do ambiente, dispositivos e permissões.
- A alteração de layout de teclado durante uma sessão e certos campos isolados podem não funcionar.

[Instalar, diagnosticar e revogar permissões do Wayland](docs/linux-wayland.md)

## Proteção, backups e compatibilidade

- Exportar e importar JSON conserva títulos, atalhos, pastas e formatação, sem substituir comandos existentes que entram em conflito.
- **Criar backup completo** produz `.aurora-backup.zip` com banco SQLite e preferências.
- **Restaurar backup** solicita confirmação, verifica estrutura e cria recuperação anterior.
- Atualizações EXE verificam hash, criam backup e só então iniciam instalador autorizado.
- Os comandos são locais. Nenhuma telemetria é enviada ao serviço de atualizações.
- **Backup em nuvem**, contas e licenciamento **Free/Premium** continuam fora desta entrega e não são afirmados como implementados.

## Arquitetura

```text
app/core.py                 banco, modelos, variáveis básicas
app/productivity_data.py    FTS5 e contadores locais
app/smart_templates.py      formulários, datas, cálculos, etapas
app/productivity_widgets.py formulários, pesquisa e painel de estatísticas
app/productivity_features.py inserção guiada e execução confirmada
app/ui_components.py        banner, menus e controles visuais compartilhados
app/ui.py                   janela e motor de integração de expansão
app/hotkeys.py              reconhecimento e ciclo de vida dos listeners
app/wayland_input.py        backend Linux Wayland experimental
app/linux_setup_ui.py       autorização orientada com consentimento
app/clipboard_content.py   transporte texto/HTML/imagem
app/updates.py              lançamentos e instaladores verificados
app/backups.py              recuperação e snapshots do perfil
```

As classes visuais foram separadas da janela principal sem alterar recursos que já eram utilizados. Outras extrações serão graduais e acompanhadas de testes.

## Construir e testar

Requer Python 3.11+:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python main.py
```

Para executar testes Qt sem ambiente gráfico:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

O workflow GitHub Actions verifica testes Windows/Linux, clipboard, Word, Chromium, binários PyInstaller, instaladores EXE/MSI/DEB e integridade dos recursos. Testes automatizados **não substituem** uma sessão real de GNOME Wayland ou versões particulares de Teams e Word.

- [Compilações GitHub Actions](https://github.com/fabriciomatosqa/AURORA-AutoFill/actions)
- [Versões publicadas](https://github.com/fabriciomatosqa/AURORA-AutoFill/releases)
- [Revisões anteriores](REVISAO.md)

## Histórico e próximos passos

A base aprovada em 19/10/2026 foi preservada e evoluiu com temas, imagens e prévia fixa; seguida por emojis Fluent e suporte experimental Wayland. Esta entrega acrescenta ferramentas de produtividade, mantendo migrações conservadoras de dados e mecanismos Windows existentes.

Fora do escopo: backup em nuvem, licenciamento, regras por aplicativo, comandos reutilizáveis e biblioteca de modelos adicionais. A assinatura digital de instaladores ainda precisa ser avaliada antes de distribuição comercial.

AURORA AutoFill — desenvolvido por Fabricio Matos.
