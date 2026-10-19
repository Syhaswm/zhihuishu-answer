[Setup]
AppId={{8F4B1C2A-6D3E-4A91-9C77-2B5E8A1D0F44}
AppName=智慧树答题
AppVersion=1.6.0
AppPublisher=Syhaswm
DefaultDirName={localappdata}\智慧树答题
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
Source: "build\portable\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Code]
function WebView2Installed: Boolean;
var
  Version: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
    Result := (Version <> '') and (Version <> '0.0.0.0');
  if not Result then
    if RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
      Result := (Version <> '') and (Version <> '0.0.0.0');
end;

[Icons]
Name: "{group}\智慧树答题"; Filename: "{app}\智慧树答题.exe"
Name: "{autodesktop}\智慧树答题"; Filename: "{app}\智慧树答题.exe"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$p=Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'; Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124701' -OutFile $p; Start-Process -FilePath $p -ArgumentList '/silent','/install' -Wait"""; StatusMsg: "正在安装界面组件..."; Flags: runhidden waituntilterminated; Check: not WebView2Installed
Filename: "{app}\智慧树答题.exe"; Description: "启动智慧树答题"; Flags: nowait postinstall skipifsilent
