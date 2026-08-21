; Hummingbird v1.0.0 EN installer (Inno Setup)
#define MyAppVersion "1.0.0"
#define MyAppName "Hummingbird"
#define MyAppFullName "Hummingbird · Local AI Assistant"
#define MyAppExe "LocalAgent.exe"

[Setup]
AppId={{B7E4F2B1-8C9D-4A5B-9E8F-1A2B3C4D5E6F}
AppName={#MyAppFullName}
AppVersion={#MyAppVersion}
AppPublisher=Gustor-Wang
AppPublisherURL=https://github.com/Gustor-Wang/hummingbird-agent
DefaultDirName={localappdata}\LocalAgent
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=Hummingbird-v1.0.0-EN-Setup
OutputDir=dist
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=LICENSE
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
UninstallDisplayName={#MyAppFullName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\LocalAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "app_lang_en.txt"; DestDir: "{app}"; DestName: "app_lang.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Code]
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;  // 永不跳过任何页面
end;

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
