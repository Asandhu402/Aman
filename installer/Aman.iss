#define MyAppName "Aman"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Aman"

[Setup]
AppId={{8A4D5D82-6A31-4D52-9F38-7B3B0A9C4E61}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Aman
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\dist\installer
OutputBaseFilename=Aman-Setup
UninstallDisplayIcon={app}\Aman.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Aman\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Aman"; Filename: "{app}\Aman.exe"
Name: "{autodesktop}\Aman"; Filename: "{app}\Aman.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Aman.exe"; Description: "Launch Aman"; Flags: postinstall nowait skipifsilent
