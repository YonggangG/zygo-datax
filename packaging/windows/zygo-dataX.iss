#define MyAppName "zygo-dataX"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "zygo-dataX"
#define MyAppExeName "zygo-dataX.exe"

[Setup]
AppId={{A5E0715D-6B0E-43E7-9B3D-5A6D0A7A0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=zygo-dataX-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\..\dist\zygo-dataX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README-WINDOWS.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\zygo-dataX"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall zygo-dataX"; Filename: "{uninstallexe}"
Name: "{autodesktop}\zygo-dataX"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch zygo-dataX"; Flags: nowait postinstall skipifsilent
