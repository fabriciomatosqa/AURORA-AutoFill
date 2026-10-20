@echo off
setlocal
cd /d "%~dp0"
title AURORA AutoFill - Gerar instalador Windows
where py >nul 2>&1
if errorlevel 1 (
 echo Python Launcher [py] nao encontrado. Instale Python 3.11 ou mais novo e tente novamente.
 pause
 exit /b 1
)
echo.
echo [1/3] Instalando dependencias de compilacao...
py -3 -m pip install -r requirements.txt pyinstaller==6.16.0 pillow
if errorlevel 1 goto error
echo.
echo [2/3] Gerando icones e compilando o aplicativo...
py -3 scripts\build_branding.py
if errorlevel 1 goto error
py -3 -m PyInstaller --noconfirm --clean --windowed --onedir --name "AURORA AutoFill" --icon "assets\aurora_icon.ico" --add-data "assets;assets" --add-data "app\accessibility_worker.ps1;app" --collect-submodules pynput main.py
if errorlevel 1 goto error
py -3 packaging\verify_bundle.py --platform windows
if errorlevel 1 goto error
echo.
for /f "delims=" %%V in ('py -3 -c "from app.version import APP_VERSION; print(APP_VERSION)"') do set "AURORA_VERSION=%%V"
if not defined AURORA_VERSION goto error
for /f "delims=" %%V in ('py -3 -c "from app.version import WINDOWS_VERSION; print(WINDOWS_VERSION)"') do set "AURORA_WINDOWS_VERSION=%%V"
if not defined AURORA_WINDOWS_VERSION goto error
echo [3/3] Criando o instalador com Inno Setup...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
 echo Inno Setup 6 nao instalado.
 echo Baixe o Inno Setup para gerar um EXE instalador.
 echo O aplicativo compilado estara em dist\AURORA AutoFill
 pause
 exit /b 1
)
"%ISCC%" "packaging\windows\AURORA-AutoFill.iss"
if errorlevel 1 goto error
echo.
echo SUCESSO: installer-win\AURORA-AutoFill-v%AURORA_VERSION%-Windows-Setup.exe
pause
exit /b 0
:error
echo.
echo Falha na compilacao. Consulte a mensagem acima.
pause
exit /b 1
