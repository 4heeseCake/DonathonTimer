; Donathon Timer — per-user Windows installer, no administrator access required.
#ifndef SourceDir
  #error SourceDir must be set via /DSourceDir=<absolute directory>
#endif
#ifndef OutputDir
  #error OutputDir must be set via /DOutputDir=<absolute directory>
#endif
#define ProductName "Donathon Timer"
#define ProductVersion "0.9.4 Beta 4"
#define VersionTag "0.9.4-beta4"

[Setup]
AppId={{B053CAED-81CB-47CA-9EA5-35A793372FAA}
AppName={#ProductName}
AppVersion={#ProductVersion}
AppPublisher=Donathon Timer
DefaultDirName={localappdata}\Programs\Donathon Timer
DefaultGroupName=Donathon Timer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\DonathonTimer.exe
SetupIconFile={#SourceDir}\..\..\buildtools\DonathonTimer.ico
OutputDir={#OutputDir}
OutputBaseFilename=DonathonTimer-{#VersionTag}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=force
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Donathon Timer"; Filename: "{app}\DonathonTimer.exe"
Name: "{autodesktop}\Donathon Timer"; Filename: "{app}\DonathonTimer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DonathonTimer.exe"; Description: "Запустить Donathon Timer"; Flags: nowait postinstall skipifsilent

; User data lives in %LOCALAPPDATA%\DonathonTimer and is NOT removed on uninstall.
