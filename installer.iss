; Chem Results GUI – Inno Setup 6 script
#define MyAppName        "Chem Results GUI"
#define MyAppExeName     "ChemResultsGUI.exe"
#ifndef MyAppVersion
#define MyAppVersion "0.0.0"
#endif
#define MyPublisher      "WL"

[Setup]
AppId={{9C02922F-0E93-418E-B510-57A77A535F30}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
DefaultDirName={pf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=ChemResultsGUISetup_{#MyAppVersion}
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}";  Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop shortcut"; Flags: unchecked
