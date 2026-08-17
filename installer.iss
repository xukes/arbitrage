; Inno Setup Script for CryptoArbitrage
; Compile with: ISCC.exe installer.iss

#define MyAppName "CryptoArbitrage"
#define MyAppNameCN "CryptoArbitrage 套利监控"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "CryptoArb"
#define MyAppURL ""
#define MyAppExeName "CryptoArbitrage.exe"
#define SourcePath "dist\CryptoArbitrage"

[Setup]
AppId={{B4E7A8D2-5F6C-4A3D-9E2B-1C8F5A7D3B6E}
AppName={#MyAppNameCN}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppNameCN}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=CryptoArbitrage_Setup_v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120,100
UninstallDisplayIcon={app}\{#MyAppExeName}

; 64-bit only
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourcePath}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppNameCN}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppNameCN}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppNameCN}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppNameCN}}"; Flags: nowait postinstall skipifsilent
