; -- monitoring_agent_setup.iss --
; Inno Setup Script for TekPossible Employee Monitoring Agent

#define MyAppName "TekPossible Monitor Agent"
#define MyAppVersion "1.0"
#define MyAppPublisher "TekPossible Inc."
; #define MyAppURL "https://www.tekpossible.com" ; Optional: Your company URL
#define MyAppExeName "monitoring_agent.exe"
; #define MyAppMutex "TekPossibleMonitorAgentRunning" ; Optional: Mutex for single instance check by installer (Code section removed for simplicity)

[Setup]
; AppId: Using your provided ID. Ensure it's unique for your application.
AppId="{{tC6cM72YI0GIKkyoGwWKJQ}}"
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; AppPublisherURL={#MyAppURL} ; Optional
; AppSupportURL={#MyAppURL}  ; Optional
; AppUpdatesURL={#MyAppURL}  ; Optional
DefaultDirName={autopf}\{#MyAppName} ; e.g., C:\Program Files (x86)\TekPossible Monitor Agent
; No Start Menu folder needed for a silent agent
DisableProgramGroupPage=yes
OutputBaseFilename=TekPossibleMonitorAgent_Setup_{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Installer requires admin rights to install to Program Files and set HKLM Run key
PrivilegesRequired=admin
; Optional: For code signing the setup.exe. If you have a signing tool, uncomment and configure it here.
; SignTool=SET_YOUR_SIGNTOOL_COMMAND_HERE
; No uninstaller will be created, and no entry in Add/Remove Programs.
Uninstallable=no 
; AppMutex={#MyAppMutex}_Setup ; Optional: Mutex for installer instance (Code section that used it is removed)


[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; This path is relative to where this .iss script is saved.
; If .iss is in '...\EMS\agent\' and .exe is in '...\EMS\agent\dist\', this is correct.
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; If your EXE has other dependencies (DLLs, etc.) that PyInstaller didn't bundle, list them here.

[Registry]
; Auto-startup for ALL users via HKLM Run key.
; This makes the agent start when any user logs into Windows.
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName} Agent"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue

; The following sections are not strictly needed for a minimal, uninstallable setup:
; [Tasks]
; [Icons]
; [UninstallRun]
; [Code] 

[Run]
; Attempt to launch the application immediately after all files are copied.
; The agent should run silently in the background.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent shellexec