# AURORA AutoFill v0.6.0

**Expansão inteligente de textos • Mais tempo para você**  
**Desenvolvido por Fabricio Matos • Versão v0.6.0**

Expansor de textos desktop para Windows e Linux, criado em Python/PySide6. Seus comandos, pastas e preferências permanecem no computador. O funcionamento principal não exige conta, internet ou assinatura.

## Novidades da v0.6.0

- **Pastas seguras:** permite excluir uma pasta; seus comandos são transferidos para outra pasta. A exclusão pode ser desfeita por **10 segundos**.
- **Comandos organizados:** arraste comandos para ordená-los. A ordem é salva no banco SQLite, inclusive ao reiniciar.
- **Exclusão de comando:** botão **Desfazer** disponível por 10 segundos.
- **Som Aurora:** novo efeito sintetizado de gota de água, estilo *glub*, com liga/desliga e volume ajustável.
- **Central de configurações:** botão ⚙ no topo ou menu da bandeja do sistema. Inclui som, volume, iniciar com o Windows, backups e atualizações.
- **Backup completo:** além de **Exportar / Importar JSON** (que já inclui todas as pastas e comandos), agora é possível criar/restaurar um arquivo `.aurora-backup.zip`, incluindo pastas, comandos, textos formatados, ordem e preferências.
- **Backup automático antes de instalar:** uma cópia de segurança é criada antes da execução de qualquer instalador baixado pelo próprio AURORA.
- **Atualizações consentidas:** consulta somente **GitHub Releases estáveis** do repositório oficial. Avisa quando há versão mais recente, pergunta antes de baixar, verifica o SHA256 e solicita confirmação para iniciar o instalador Windows. Não executa atualizações silenciosas.
- **Versão centralizada:** interface, instaladores e arquivos distribuídos utilizam a versão definida em `app/version.py`.
- **Visual Aurora Boreal:** identidade original preservada, menu de comandos dinâmicos arredondado e editor/prévia ampliados na proporção 60/40.

Os formulários dinâmicos ainda **não foram implementados**; estão fora do escopo desta versão.

## Baixar e instalar

### Versões estáveis

Acesse [GitHub Releases](https://github.com/fabriciomatosqa/AURORA-AutoFill/releases). Apenas versões testadas e aprovadas são publicadas nesse local. As Releases antigas permanecem disponíveis como pontos de recuperação (ao contrário dos artifacts temporários).

- **Windows:** baixe `AURORA-AutoFill-vX.Y.Z-Windows-Setup.exe`. Não precisa instalar Python.
- **Linux Ubuntu 24.04 amd64:** baixe o arquivo `.deb` e instale com `sudo apt install ./arquivo.deb`. Também há `.tar.gz` portátil. Atalhos globais dependem de X11/Xorg; Wayland pode restringir a captura.

### Compilações de desenvolvimento

Acesse [GitHub Actions](https://github.com/fabriciomatosqa/AURORA-AutoFill/actions/workflows/build-installers.yml) para os instaladores de teste. Cada push no branch `dev/correcao-expansao-windows` inicia a compilação automaticamente. Abra a execução aprovada e baixe o artifact **Windows** ou **Linux**. Os artifacts expiram depois de 30 dias.

> A versão v0.6.0 permanece em desenvolvimento até a aprovação dos testes manuais. Um artifact de desenvolvimento não é uma Release estável, portanto não dispara atualizações automáticas nos computadores já instalados.

## Backup e restauração

O banco do AURORA armazena *todas* as pastas e snippets:

- Windows: `%APPDATA%\AutoFillStudio\snippets.sqlite3`
- Linux: `~/.local/share/AutoFillStudio/snippets.sqlite3`
- Preferências: arquivo `settings.json` no mesmo diretório.
- Backups completos: subpasta `backups`.

**Exportar** já reúne todas as pastas, atalhos e conteúdos, incluindo formatação. **Importar** acrescenta dados sem apagar os existentes (atalhos repetidos podem ser ignorados). Já **Restaurar backup completo** substitui o banco atual pelo snapshot selecionado: requer confirmação e cria uma cópia de segurança antes da operação.

Backups manuais não são apagados automaticamente. Cópias pré-atualização podem usar retenção limitada para economizar espaço.

## Atualização online e privacidade

1. Ao iniciar, se a preferência estiver habilitada, o programa consulta a versão estável mais recente no GitHub.
2. Se houver versão mais nova, pergunta se você deseja baixar.
3. No Windows instalado, baixa o EXE da Release oficial e verifica o SHA256 fornecido nos assets da mesma Release.
4. Pede confirmação novamente, cria backup completo, inicia o instalador e encerra o AURORA. O instalador apresenta seu assistente normal.
5. No Linux, oferece a página da Release para atualizar manualmente o pacote; não executa comandos administrativos sem intervenção.

O aplicativo não envia conteúdos dos seus comandos para o GitHub. Apenas a consulta opcional de versão usa a rede.

## Desenvolvimento e testes

Python 3.11+:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python main.py
```

O build GitHub Actions executa testes automatizados e smoke tests de executáveis antes de criar os instaladores.

### Publicação de uma versão estável

Depois de validar **Windows e Linux** e revisar o commit, crie intencionalmente uma tag anotada `vX.Y.Z`, correspondente à versão em `app/version.py`, e envie a tag ao GitHub. O workflow compila novamente ambos os sistemas; somente se os dois jobs passarem, publica o instalador Windows, os pacotes Linux e os checksums no **GitHub Releases**. Nenhuma tag ou release estável é criada apenas por push no branch de desenvolvimento.

Para preservar pontos de recuperação, **não remova as últimas três Releases estáveis**. Releases não expiram como os artifacts temporários. O histórico Git também continua preservado.

## Limitações conhecidas

- O posicionamento do cursor e a colagem dependem do editor de destino. Teste Word, Bloco de Notas, navegadores e Teams nas versões instaladas.
- Linux/Wayland restringe atalhos globais; prefira X11/Xorg para essa função.
- Iniciar com Windows é recurso da versão instalada Windows e usa a chave `Run` do usuário atual, sem exigir privilégios administrativos.
- Um aplicativo ainda não assinado digitalmente pode exibir alertas do Windows SmartScreen. Antes de distribuir publicamente, avaliar assinatura de código.
