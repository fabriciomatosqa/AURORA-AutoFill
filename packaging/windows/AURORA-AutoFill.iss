#define AppName "AURORA AutoFill"
#define AppVersion GetEnv("AURORA_VERSION")
#define WindowsVersion GetEnv("AURORA_WINDOWS_VERSION")
#if AppVersion == ""
  #error "Defina AURORA_VERSION a partir de app.version antes de compilar"
#endif
#if WindowsVersion == ""
  #error "Defina AURORA_WINDOWS_VERSION a partir de app.version antes de compilar"
#endif
#define AppPublisher "Fabricio Matos"
#define AppExeName "AURORA AutoFill.exe"

[Setup]
SourceDir=..\..
AppId={{6C34F9C8-9F89-4D4B-B894-0F33A4A0D379}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\AURORA AutoFill
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
ShowLanguageDialog=no
OutputDir=installer-win
OutputBaseFilename=AURORA-AutoFill-v{#AppVersion}-Windows-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=assets\aurora_icon.ico
VersionInfoVersion={#WindowsVersion}
VersionInfoTextVersion={#AppVersion}
CloseApplications=yes
RestartApplications=no
VersionInfoDescription=Instalador do AURORA AutoFill

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "dist\AURORA AutoFill\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AURORA AutoFill"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\AURORA AutoFill"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Executar AURORA AutoFill"; Flags: nowait postinstall skipifsilent; Check: not IsAuroraUpdate
Filename: "{app}\{#AppExeName}"; Flags: nowait runasoriginaluser; Check: IsAuroraUpdate

[Code]
const
  AuroraUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6C34F9C8-9F89-4D4B-B894-0F33A4A0D379}_is1';

function IsAuroraUpdate: Boolean;
begin
  { Silent deployment alone must not start the app; only an in-app update does. }
  Result := ExpandConstant('{param:AURORAUPDATE|0}') = '1';
end;

function InitializeSetup: Boolean;
var
  InstalledDir: String;
  Parameters: String;
  ChildExitCode: Integer;
begin
  Result := True;
  if IsAuroraUpdate then
    Log('AURORA: in-app update; silent=' + IntToStr(Ord(WizardSilent)));

  { The installed 0.6.1-161026 updater passed only /NORESTART. Recognize that
    exact invocation, not a normal double-click or arbitrary deployment flags,
    and hand off before the wizard is created. New updaters pass the explicit
    marker and silent flags directly, so this branch cannot recurse. }
  if (not WizardSilent) and (not IsAuroraUpdate) and
     (ParamCount = 1) and (CompareText(ParamStr(1), '/NORESTART') = 0) and
     RegQueryStringValue(HKCU, AuroraUninstallKey, 'InstallLocation', InstalledDir) and
     FileExists(AddBackslash(InstalledDir) + '{#AppExeName}') then
  begin
    Log('AURORA: legacy updater detected; handing off without a wizard.');
    Parameters := '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- ' +
      '/CLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /AURORAUPDATE=1 /LOG ' +
      '/DIR=' + AddQuotes(InstalledDir);
    if not Exec(ExpandConstant('{srcexe}'), Parameters, '', SW_HIDE,
       ewWaitUntilTerminated, ChildExitCode) then
      SuppressibleMsgBox('Não foi possível iniciar a atualização do AURORA AutoFill. ' +
        'Abra o programa e tente novamente.', mbError, MB_OK, IDOK)
    else if ChildExitCode <> 0 then
      SuppressibleMsgBox('A atualização não foi concluída. Abra o AURORA AutoFill ' +
        'e tente novamente. Código: ' + IntToStr(ChildExitCode), mbError, MB_OK, IDOK);
    Result := False;
  end;
end;
