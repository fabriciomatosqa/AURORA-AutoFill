# AURORA AutoFill

**Expansão inteligente de textos • Mais tempo para você**  
Desenvolvido por Fabricio Matos

Expansor de textos desktop para Windows e Linux, criado em Python/PySide6. Organize comandos em pastas, escreva um atalho como `/resposta` e insira o texto em outros aplicativos. Os comandos, a formatação e as preferências ficam neste computador; a expansão não exige conta ou conexão com a internet.

## Instalar e atualizar

Baixe os instaladores na página oficial de [GitHub Releases](https://github.com/fabriciomatosqa/AURORA-AutoFill/releases). **Durante o desenvolvimento, os lançamentos marcados como Pre-release são versões de teste e também aparecem no atualizador do aplicativo.**

**Receber versões de teste** vem ativado nas compilações de desenvolvimento. Para acompanhar somente versões estáveis, desmarque essa opção nas configurações; sua escolha fica salva.

- **Windows:** baixe `AURORA-AutoFill-v<versão>-Windows-Setup.exe`. Não precisa instalar Python. Instale sobre a versão anterior, sem desinstalar o aplicativo nem apagar seus dados.
- **Ubuntu 24.04 amd64:** baixe o `.deb` e abra no gerenciador de pacotes, ou use `sudo apt install ./arquivo.deb`. Há também um `.tar.gz` portátil.

**Primeira migração da v0.6.0:** é necessário baixar e instalar esta nova compilação uma vez. O atualizador antigo procurava exclusivamente lançamentos estáveis e não consegue descobrir versões de teste. Depois dessa migração, use **⚙ Configurações → Verificar atualizações agora**; as próximas compilações poderão ser baixadas pelo programa.

### Como funciona a atualização pelo aplicativo

1. Ao iniciar, o AURORA consulta os lançamentos oficiais do repositório `fabriciomatosqa/AURORA-AutoFill`, se a opção de avisar estiver habilitada. Também é possível verificar manualmente nas configurações.
2. Compara a versão instalada com as publicadas, incluindo versões de teste com data como `0.6.1-161026` (16/10/2026). As datas são comparadas pelo calendário, inclusive na virada de mês e ano. Rascunhos e versões antigas não são oferecidos. O instalador precisa ser compatível com o sistema.
3. Pede confirmação para baixar e mostra o progresso, com opção de cancelar. A consulta e o download ocorrem em segundo plano.
4. Confere a integridade SHA256 do arquivo baixado e pede confirmação para instalar.
5. Cria um backup completo **antes** de abrir o instalador. Se o backup ou a verificação falhar, a instalação não é iniciada.
6. No Windows, abre o assistente do instalador e fecha o AURORA. No Linux, abre o `.deb` no gerenciador de pacotes; a confirmação e eventuais permissões são solicitadas pelo sistema. Se não houver gerenciador associado, a atualização pode ser instalada manualmente pela Release.

Nenhum comando ou conteúdo pessoal é enviado ao GitHub. A rede é usada para consultar lançamentos e baixar o instalador escolhido. SHA256 verifica a integridade em relação aos arquivos publicados; o instalador ainda não possui assinatura de código.

## Recursos

- **Pastas e ordenação:** arraste comandos para reorganizar; a ordem permanece salva ao reiniciar. Excluir uma pasta transfere seus comandos para outra pasta.
- **Desfazer por 10 segundos:** ao excluir um comando ou uma pasta, use o aviso no rodapé para recuperar a operação.
- **Editor e prévia 60/40:** edição com formatação e visualização do texto final.
- **Variáveis:** data, hora, área de transferência e marcador `{{cursor}}`.
- **Gota de confirmação:** som original sintetizado, curto e suave, estilo *glube*. Liga/desliga e volume nas configurações.
- **Central de configurações:** áudio, início com Windows, backups e atualizações, sem acrescentar botões à tela principal.
- **Visual Aurora:** azul noite e ciano, menus arredondados e configurações integradas ao tema.
- **Uma instância por perfil:** impede que duas cópias do programa processem o mesmo atalho simultaneamente. Se já estiver aberto, acesse o ícone próximo ao relógio.

**Formulários dinâmicos não foram implementados** e continuam aguardando avaliação.

## Proteger e recuperar os dados

**Exportar JSON** inclui todas as pastas e todos os comandos, com formatação e ordem. **Importar JSON** acrescenta os dados ao banco atual; não apaga comandos existentes e ignora atalhos já cadastrados. Pastas vazias também são preservadas.

**Criar backup completo** salva um `.aurora-backup.zip` com o banco SQLite e as preferências. **Restaurar backup** substitui os dados atuais pelos do arquivo selecionado, após confirmação. Uma cópia de segurança é criada antes de restaurar. A estrutura do arquivo é validada antes da substituição.

Os arquivos ficam em:

| Dados | Windows | Linux |
| --- | --- | --- |
| Pasta de dados | `%APPDATA%\AutoFillStudio` | `~/.local/share/AutoFillStudio` |
| Banco | `snippets.sqlite3` | `snippets.sqlite3` |
| Preferências | `settings.json` | `settings.json` |
| Backups completos | Subpasta `backups` | Subpasta `backups` |

Backups manuais não são apagados automaticamente. Backups automáticos pré-atualização mantêm as últimas cinco cópias. O botão **Abrir backups** abre a pasta de recuperação.

## Compilações e histórico de versões

Cada push em `dev/correcao-expansao-windows` ou `main` executa [os testes e a compilação Windows/Linux](https://github.com/fabriciomatosqa/AURORA-AutoFill/actions/workflows/build-installers.yml). Somente depois de ambos os sistemas passarem, os instaladores e os checksums são publicados juntos em uma **Pre-release**. A versão usa `BASE-DDMMAA`, por exemplo `0.6.1-161026`, com a data no horário de Brasília. Uma segunda atualização no mesmo dia recebe `.2`, a terceira `.3`, preservando as publicações anteriores. Repetir uma compilação do mesmo commit reutiliza sua versão.

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

O GitHub Actions também verifica os recursos empacotados, inicia os executáveis compilados em perfis temporários e confirma a preservação dos dados antes de publicar os instaladores. Depois da publicação, o atualizador novo e o código exato do atualizador da `0.6.1-dev.22.1` consultam e baixam os instaladores Windows/Linux, verificando o SHA256 sem executá-los. O efeito sonoro pode ser reproduzido com `python tools/generate_feedback.py`.

## Limitações e validação manual

- A colagem e o posicionamento do cursor dependem do aplicativo de destino. Valide com as versões de Word, Bloco de Notas, navegadores e Teams utilizadas no seu computador.
- Linux exige X11/Xorg para atalhos globais; Wayland pode impedir a captura. O DEB distribuído é voltado a Ubuntu 24.04 amd64.
- Iniciar com Windows está disponível no aplicativo Windows instalado e usa a chave `Run` do usuário atual.
- O instalador Windows não está assinado digitalmente; o Windows pode exibir o aviso do SmartScreen.
- A fonte em desenvolvimento abre a página da Release para instalar o pacote. A substituição da própria cópia está disponível nos aplicativos empacotados.
