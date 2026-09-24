; Inno Setup script for Umbra.
; Build the app first (build.ps1), then either run  build.ps1 -Setup  or compile this
; file in the Inno Setup IDE. Output: dist\Umbra-Setup.exe

#ifndef AppVersion
  #define AppVersion "1.0.1"
#endif
#define AppName "Umbra"
#define AppExe "Umbra.exe"
#define AppPublisher "Sihab Sahariar"
#define AppURL "https://sihabsahariar.github.io/Umbra/"
#define RepoURL "https://github.com/SihabSahariar/Umbra"

[Setup]
; Keep this AppId forever - it is how Windows recognises upgrades of the same app.
AppId={{ECF922D7-B440-4D3F-A7AD-B2F9AC0BBC06}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#RepoURL}/issues
AppUpdatesURL={#RepoURL}/releases
AppCopyright=Copyright (C) 2026 {#AppPublisher}
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup

; Per-user install by default (no admin prompt); the user may choose "all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

LicenseFile=..\LICENSE
SetupIconFile=..\assets\umbra-brand\icons\umbra.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=wizard-large-1x.bmp,wizard-large-2x.bmp
WizardSmallImageFile=wizard-small-1x.bmp,wizard-small-2x.bmp

OutputDir=..\dist
; Fixed name so https://github.com/SihabSahariar/Umbra/releases/latest/download/Umbra-Setup.exe always works.
OutputBaseFilename=Umbra-Setup
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4

; Umbra runs in the tray; close it so its files can be replaced or removed.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Start {#AppName} when I sign in to Windows"; GroupDescription: "Startup:"

[Files]
Source: "..\dist\Umbra\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Privacy screen - hides your display when you look away"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same per-user Run entry that Umbra's own "Start with Windows" setting manages.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; \
  ValueData: """{app}\{#AppExe}"" --background"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "StopUmbra"

[Code]
procedure StopRunningUmbra;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningUmbra;  { upgrading while Umbra sits in the tray }
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { Remove the start-up entry whether the installer or the app created it. }
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#AppName}');
    if DirExists(ExpandConstant('{userappdata}\{#AppName}')) and
       (SuppressibleMsgBox('Also remove your Umbra settings, calibration and logs?',
                           mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES) then
      DelTree(ExpandConstant('{userappdata}\{#AppName}'), True, True, True);
  end;
end;
