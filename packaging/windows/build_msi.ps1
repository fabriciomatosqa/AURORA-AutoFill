$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..\..'))

$bundle = (Resolve-Path 'dist/AURORA AutoFill').Path
$program = Join-Path $bundle 'AURORA AutoFill.exe'
if (!(Test-Path $program)) { throw 'PyInstaller EXE nao encontrado para o MSI.' }

$wixBinaries = @(
  "${env:ProgramFiles(x86)}\WiX Toolset v3.14\bin",
  "${env:ProgramFiles(x86)}\WiX Toolset v3.11\bin"
)
$wixFolder = $wixBinaries | Where-Object {
  Test-Path (Join-Path $_ 'heat.exe')
} | Select-Object -First 1
if (!$wixFolder) {
  choco install wixtoolset --version 3.14.1.20250415 -y --no-progress
  if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel instalar o WiX v3.' }
  $wixFolder = $wixBinaries | Where-Object {
    Test-Path (Join-Path $_ 'heat.exe')
  } | Select-Object -First 1
}
if (!$wixFolder) { throw 'heat.exe nao localizado apos instalar WiX Toolset.' }
$heat = Join-Path $wixFolder 'heat.exe'
$candle = Join-Path $wixFolder 'candle.exe'
$light = Join-Path $wixFolder 'light.exe'

$version = (python -c 'from app.version import APP_VERSION; print(APP_VERSION)').Trim()
$msiVersion = (python packaging/windows/msi_version.py --version $version).Trim()
if ($LASTEXITCODE -ne 0 -or !$msiVersion) { throw 'Falha ao calcular ProductVersion MSI.' }
Write-Host "Versao AURORA=$version; ProductVersion MSI=$msiVersion"

$work = Join-Path $env:RUNNER_TEMP 'aurora-wix'
New-Item -ItemType Directory -Force $work | Out-Null
$harvest = Join-Path $work 'ApplicationFiles.wxs'
& $heat dir $bundle -nologo -cg AuroraApplicationFiles -dr INSTALLFOLDER -srd -scom -sreg -ag -var var.SourceDir -out $harvest
if ($LASTEXITCODE -ne 0) { throw 'WiX heat falhou ao coletar PyInstaller.' }
python packaging/windows/fix_msi_components.py $harvest
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel preparar componentes MSI por usuario.' }
& $candle -nologo -arch x64 "-dSourceDir=$bundle" "-dMsiVersion=$msiVersion" -out (Join-Path $work 'Aurora.wixobj') 'packaging/windows/AURORA-AutoFill.wxs'
if ($LASTEXITCODE -ne 0) { throw 'WiX candle falhou no projeto MSI.' }
& $candle -nologo -arch x64 "-dSourceDir=$bundle" -out (Join-Path $work 'ApplicationFiles.wixobj') $harvest
if ($LASTEXITCODE -ne 0) { throw 'WiX candle falhou na lista dos arquivos.' }

New-Item -ItemType Directory -Force installer-win | Out-Null
$output = "installer-win/AURORA-AutoFill-v$version-Windows-x64.msi"
& $light -nologo -out $output (Join-Path $work 'Aurora.wixobj') (Join-Path $work 'ApplicationFiles.wixobj')
if ($LASTEXITCODE -ne 0) { throw 'WiX light nao conseguiu vincular o MSI.' }
if (!(Test-Path $output)) { throw 'MSI nao foi gerado.' }
Write-Host "MSI gerado: $output"
