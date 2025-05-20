; -- monitoring_agent_setup.iss --
; Inno Setup Script for TekPossible Employee Monitoring Agent

#define MyAppName "TekPossible Monitor Agent"
#define MyAppVersion "1.0"
#define MyAppPublisher "TekPossible Inc."
#define MyAppExeName "monitoring_agent.exe"

[Setup]
; AppId: Use a unique GUID for your application.
; Generate one from https://www.guidgenerator.com/ and replace the example below.
AppId="{{tC6cM72YI0GIKkyoGwWKJQ}}" ; <<< !!! REPLACE WITH YOUR OWN NEW, STANDARD FORMAT GUID !!!
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName} ; Installs to Program Files directory
; No Start Menu folder will be created
DisableProgramGroupPage=yes
OutputBaseFilename=TekPossibleMonitorAgent_Setup_{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Installer requires administrator privileges
PrivilegesRequired=admin
; Setting Uninstallable to 'no' means no uninstaller is created and no Add/Remove Programs entry.
Uninstallable=no 

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Source path is relative to where this .iss script is saved.
; This assumes 'monitoring_agent.exe' is in a 'dist' subfolder.
; Example: If .iss is in 'C:\project\agent\' and .exe is in 'C:\project\agent\dist\'.
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; If your EXE has other essential files (DLLs, config files not bundled by PyInstaller),
; list them here to be copied to {app} as well.

[Registry]
; Auto-startup for ALL users via HKEY_LOCAL_MACHINE Run key.
; This makes the agent start when any user logs into Windows.
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName} Agent"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue

[Run]
; Attempt to launch the application immediately after all files are copied.
; The agent should run silently in the background.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent shellexec