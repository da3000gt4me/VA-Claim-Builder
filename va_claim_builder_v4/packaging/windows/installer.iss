
#define MyAppName "VA Claim Builder"
#define MyAppVersion "4.2.0 RC4"
#define MyAppExeName "VAClaimBuilder.exe"
#ifndef MySourceDir
#define MySourceDir "..\..\dist\VAClaimBuilder"
#endif
#ifndef MyOutputDir
#define MyOutputDir "dist-installer"
#endif
[Setup]
AppId={{7E0305E4-2350-4EE8-A4BB-12C19A445B91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\VA Claim Builder
DefaultGroupName={#MyAppName}
OutputDir={#MyOutputDir}
OutputBaseFilename=VA_Claim_Builder_4.2.0_RC4_Windows_x64_Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
