; 鸣鸟 v1.4.0 中文安装程序(2026-09 品牌更名;输出文件名用 ASCII,GitHub Release 资产名不支持中文) (Inno Setup)
#define MyAppVersion "1.4.0"
#define MyAppName "鸣鸟"
#define MyAppFullName "鸣鸟 · 本地 AI 助手"
#define MyAppExe "LocalAgent.exe"

[Setup]
AppId={{C8F5A3C2-9D0E-4B6C-8F9A-2B3C4D5E6F70}
AppName={#MyAppFullName}
AppVersion={#MyAppVersion}
AppPublisher=Gustor-Wang
AppPublisherURL=https://github.com/Mingbird/Mingbird-agent
DefaultDirName={localappdata}\Mingbird
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=Mingbird-v1.4.0-CN-Setup
OutputDir=dist
SetupIconFile=app.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=LICENSE
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
UninstallDisplayName={#MyAppFullName}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\LocalAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "app_lang_zh.txt"; DestDir: "{app}"; DestName: "app_lang.txt"; Flags: ignoreversion

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
