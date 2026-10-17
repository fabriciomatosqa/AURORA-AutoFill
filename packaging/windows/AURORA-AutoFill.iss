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
DisableStartupPrompt=yes
SetupLogging=yes
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

var
  LegacyAutoUpdate: Boolean;

function IsAuroraUpdate: Boolean;
begin
  { Silent deployment alone must not start the app; only an in-app update does. }
  Result := LegacyAutoUpdate or (ExpandConstant('{param:AURORAUPDATE|0}') = '1');
end;

function InitializeSetup: Boolean;
var
  InstalledDir: String;
  ParameterIndex: Integer;
  LegacyRequest: Boolean;
  HasPreviousInstall: Boolean;
  PreviousExeExists: Boolean;
begin
  Result := True;
  LegacyAutoUpdate := False;
  Log('AURORA: initializing; params=' + IntToStr(ParamCount));
  for ParameterIndex := 1 to ParamCount do
    Log('AURORA: parameter ' + IntToStr(ParameterIndex) + ': ' + ParamStr(ParameterIndex));
  if IsAuroraUpdate then
    Log('AURORA: in-app update; silent=' + IntToStr(Ord(WizardSilent)));

  { The installed 0.6.1-161026 updater passed only /NORESTART. Recognize that
    exact invocation, not a normal double-click or arbitrary deployment flags,
    and continue automatically in this same installer. New updaters pass the
    explicit marker and silent flags directly. Executing Setup itself before
    installation is deliberately prohibited by Inno Setup; no self-relaunch
    or security override is used here. }
  LegacyRequest := (not WizardSilent) and (not IsAuroraUpdate) and
    (ParamCount = 1) and (CompareText(ParamStr(1), '/NORESTART') = 0);
  if not LegacyRequest then
    Exit;
  { Resolve the registered directory before checking its executable, keeping
    each validation and its diagnostic message separate. }
  InstalledDir := '';
  HasPreviousInstall := RegQueryStringValue(HKCU, AuroraUninstallKey,
    'InstallLocation', InstalledDir);
  Log('AURORA: previous installation registered=' + IntToStr(Ord(HasPreviousInstall)) +
    '; directory=' + InstalledDir);
  if not HasPreviousInstall then
    Exit;
  PreviousExeExists := FileExists(AddBackslash(InstalledDir) + '{#AppExeName}');
  Log('AURORA: previous executable exists=' + IntToStr(Ord(PreviousExeExists)));
  if PreviousExeExists then
  begin
    LegacyAutoUpdate := True;
    Log('AURORA: legacy updater detected; automatic update in existing setup.');
  end;
end;

procedure InitializeWizard;
begin
  if LegacyAutoUpdate then
    WizardForm.Caption := 'Atualizando AURORA AutoFill';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { Inno's normal ClickToStartPage flow advances automatically when every
    choice page is skipped. Preparing/installing still use the normal engine;
    this one-time transition shows progress and requires no Next/Finish clicks. }
  Result := LegacyAutoUpdate;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if LegacyAutoUpdate and (CurStep = ssDone) then
    Log('AURORA: legacy automatic update completed.');
end;
