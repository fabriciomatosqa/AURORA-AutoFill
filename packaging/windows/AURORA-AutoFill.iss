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
Filename: "{app}\{#AppExeName}"; Description: "Executar AURORA AutoFill"; Flags: nowait postinstall skipifsilent
