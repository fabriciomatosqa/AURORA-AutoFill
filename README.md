# AURORA AutoFill v0.5.1

**Expansão inteligente de textos · Mais tempo para você**  
**Desenvolvido por Fabricio Matos**

Aplicativo desktop nativo em Python/PySide6 para criar atalhos de expansão de texto e reutilizá-los em outros programas. A interface utiliza uma identidade visual de aurora boreal, com marcadores dinâmicos, pastas e editor de texto rico.

## Novidades da v0.5.1

- Nova assinatura visual **AURORA AutoFill** com letras de espaçamento controlado e leve degradê, sem depender de fontes baixadas ou embarcadas.
- Menus de pastas desenhados como menus escuros consistentes (evitam aquela borda cinza e fundo branco do seletor do sistema).
- Destaques e indicadores em verde-água na seleção.
- Crédito fixo no canto direito do rodapé: **Desenvolvido por Fabricio Matos • 2026**.
- Banner com a aurora, as montanhas e o lago visíveis, preservado da v0.5.
- Mantidos atalhos globais, pastas, comandos dinâmicos, importação/exportação, formatação e bandeja do sistema.

## Instalação — Windows

Baixe nos **Artifacts** do [GitHub Actions](https://github.com/fabriciomatosqa/AURORA-AutoFill/actions) o instalador
`AURORA-AutoFill-v0.5.1-Windows-Setup.exe` e execute-o. Ele instala o aplicativo, cria atalhos no menu Iniciar e oferece atalho na área de trabalho. **Não é necessário instalar Python**.

A compilação Windows é feita num runner **Windows** com PyInstaller e Inno Setup. Ela não pode ser gerada corretamente num host Linux sem uma ferramenta de compilação cruzada preparada.

## Instalação — Linux Ubuntu/Debian

Baixe `AURORA-AutoFill-v0.5.1-Linux-amd64.deb` no GitHub Actions. Instale com:

```bash
sudo apt install ./AURORA-AutoFill-v0.5.1-Linux-amd64.deb
```

Abra o programa pelo menu de aplicativos como **AURORA AutoFill** ou execute `aurora-autofill`. **A função de atalhos globais exige uma sessão X11/Xorg**. Em Wayland, a interface funciona, mas a captura de atalhos globais fica restrita.

O pacote `.deb` gerado pelo GitHub Actions embute o executável empacotado pelo PyInstaller e **não requer Python**.

Também existe uma edição `.deb` **Bootstrap / Offline** (compilada neste ambiente) que contém rodas locais do PySide6 para instalação no primeiro uso, precisa de `python3-venv` e Python 3.10+ e foi feita como alternativa para testes enquanto o GitHub Actions compila as edições finais. Ela é específica de Linux amd64/glibc ≥ 2.34.

## Executar a partir do código-fonte

Python 3.11+ (3.13 recomendado):

```bash
python -m pip install -r requirements.txt
python main.py
```

Para Windows, também existe `iniciar_windows.bat`; para Linux X11, `iniciar_linux.sh`.

## Compilação automatizada dos instaladores

O arquivo `.github/workflows/build-installers.yml` executa testes, compila o aplicativo com PyInstaller e gera um **instalador EXE Windows** com Inno Setup e um **DEB Linux**. Em GitHub → **Actions** → **Compilar instaladores AURORA AutoFill** → **Run workflow**. Ao terminar, os instaladores aparecem em **Artifacts**.

## Dados, atualização e privacidade

- Os dados existentes permanecem no SQLite em `%APPDATA%\AutoFillStudio\snippets.sqlite3` (Windows) ou `~/.local/share/AutoFillStudio/snippets.sqlite3` (Linux).
- O programa não sincroniza nem envia conteúdos para um servidor. O monitor de teclado mantém somente um buffer pequeno **em memória**, para reconhecer atalhos.
- Faça backup em **Exportar** antes de mudar de versão.
- O botão **X** oculta na bandeja do sistema, quando suportada. Use o menu **Encerrar** no ícone para sair de verdade.

## Testes

```bash
python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen AURORA_AUTOFILL_SMOKE_TEST=1 python main.py  # Linux
```

Teste de criação/edição, captura de atalhos em apps externos e bandeja requerem validação real em Windows e/ou Linux X11, pois ambientes offscreen não expõem uma área de trabalho completa.