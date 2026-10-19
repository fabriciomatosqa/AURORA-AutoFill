# AURORA AutoFill v0.5.2

**Expansão inteligente de textos • Mais tempo para você**  
**Desenvolvido por Fabricio Matos • 2026**  
[Repositório do projeto](https://github.com/fabriciomatosqa/AURORA-AutoFill)

Expansor de texto desktop para Windows e Linux, em Python/PySide6. Cadastra atalhos, organiza por pastas, mantém os dados localmente e substitui atalhos em outros aplicativos.

## O que mudou na v0.5.2

- **Banner panorâmico corrigido:** a paisagem em alta resolução agora é desenhada num componente com recorte proporcional, sem a deformação de `border-image stretch`.
- **Marca tipográfica revisada:** desenho vetorial com tipografia mais forte, refinamento no gradiente e um filete inspirado na aurora boreal. O resultado pode variar ligeiramente conforme as fontes disponíveis no sistema.
- **Compatibilidade com Bloco de Notas (Windows 10/11):** a expansão é iniciada após liberar a última tecla e esperar um curto intervalo. O conteúdo é enviado pelo clipboard usando Unicode e Ctrl+V em vez de eventos individuais para cada letra; modelos realmente formatados continuam incluindo HTML para Word/Outlook.
- **Área de transferência:** o conteúdo anterior é recuperado após a expansão se o usuário não tiver copiado outro item enquanto isso.
- **Som de confirmação:** clique `.wav` original, sintetizado especificamente para este projeto, reproduzido de maneira assíncrona após enviar o comando. Sem samples de terceiros e sem QtMultimedia.
- **Linux:** teste aprimorado no GitHub Actions, incluindo bibliotecas X11, execução offscreen e validação sob Xvfb, além de conferir que o banner e o arquivo de som foram incluídos no executável.
- **Rodapé:** crédito permanente: *Desenvolvido por Fabricio Matos • 2026*.

## Primeira instalação: Conheça o AURORA

Em uma instalação realmente nova (sem banco de dados anterior), o aplicativo cria a pasta **Conheça o AURORA** com quatro exemplos editáveis:

- `/bemvindo` — apresenta o AURORA AutoFill e seus benefícios.
- `/tutorial` — ensina a criar atalhos e organizar conteúdos em pastas.
- `/datahora` — demonstra os marcadores dinâmicos `{{data}}`, `{{hora}}` e `{{data_hora}}`.
- `/obrigado` — agradece pela instalação e compartilha uma mensagem motivacional.

A pasta inicial pode ser editada e os exemplos podem ser apagados. **Bancos de dados já existentes, inclusive vazios, não recebem esses exemplos novamente**, para preservar exclusões, dados próprios e backups importados. Atualizações não removem nem alteram atalhos antigos.


Acesse [Actions](https://github.com/fabriciomatosqa/AURORA-AutoFill/actions), abra a execução de **Compilar instaladores AURORA AutoFill**, baixe o artefato `AURORA-AutoFill-v0.5.2-Windows-Setup` e extraia o instalador `.exe`.

A configuração usa GitHub Actions + PyInstaller + Inno Setup no Windows. O usuário final não precisa instalar Python. Para gerar localmente no Windows, execute `gerar_instalador_windows.bat` com Python e Inno Setup instalados.

## Instalar no Linux (Ubuntu/Debian, amd64)

No mesmo Actions, baixe `AURORA-AutoFill-v0.5.2-Linux`, extraia o `.deb` e instale com:

```bash
sudo apt install ./AURORA-AutoFill-v0.5.2-Linux-amd64.deb
```

Execute pelo menu de aplicativos ou digitando `aurora-autofill` no terminal. Há ainda uma versão `.tar.gz` portátil. Os atalhos globais dependem de X11/Xorg; o Wayland restringe a captura de teclas por outros aplicativos. O feedback sonoro no Linux usa `paplay`, `pw-play` ou `aplay` se disponíveis, com beep do Qt como alternativa.

## Executar pelo código-fonte

Python 3.11+:

```bash
python -m pip install -r requirements.txt
python main.py
```

## Testes

```bash
python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen AURORA_AUTOFILL_SMOKE_TEST=1 python main.py
```

**Limites importantes:** o fluxo de colagem foi criado para aumentar a compatibilidade com Notepad, navegadores, Word e editores comuns, mas nenhum injetor de teclas consegue garantir funcionamento em *todos* os programas, especialmente aplicativos elevados/protegidos, campos de senha, jogos e sessões remotas. A correção do Notepad foi verificada em testes de eventos Win32 simulados; deve ser validada em um Windows real antes de considerá-la definitiva.

## Dados e privacidade

- Windows: `%APPDATA%\AutoFillStudio\snippets.sqlite3`.
- Linux: `~/.local/share/AutoFillStudio/snippets.sqlite3`.
- O aplicativo funciona localmente, sem enviar textos para servidores.
- Seus atalhos e pastas continuam preservados após atualizações.
- Use **Exportar** para fazer backup antes de instalar uma nova versão.
- Ao clicar no **X**, a janela fica na bandeja do sistema, onde suportado; selecione **Encerrar** no ícone para fechar de fato.