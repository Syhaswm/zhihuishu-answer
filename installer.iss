[Setup]
AppId={{8F4B1C2A-6D3E-4A91-9C77-2B5E8A1D0F44}
AppName=智慧树答题
AppVersion=1.4.0
AppPublisher=Syhaswm
DefaultDirName={autopf}\智慧树答题
DefaultGroupName=智慧树答题
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=智慧树答题-Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\智慧树答题.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\智慧树答题\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\智慧树答题"; Filename: "{app}\智慧树答题.exe"
Name: "{autodesktop}\智慧树答题"; Filename: "{app}\智慧树答题.exe"

[Run]
Filename: "{app}\智慧树答题.exe"; Description: "启动智慧树答题"; Flags: nowait postinstall skipifsilent
