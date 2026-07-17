#define MyAppName "Subtitle Burner"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Subtitle Burner"

[Setup]
AppId={{7E6B2D5A-9C1F-4B8E-9F2A-3D6C7E4A1B90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL=https://github.com/
DefaultDirName={autopf}\SubtitleBurner
DefaultGroupName=Subtitle Burner
DisableProgramGroupPage=yes
; Per-user install only: the app writes its own config/job files under {app}
; at runtime, which requires {app} to always be user-writable. A per-machine
; (admin/Program Files) install would break that, so this intentionally does
; not offer the elevated/system-wide alternative - same choice most consumer
; app installers (Chrome, Discord, VS Code's default download) make.
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=SubtitleBurnerSetup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
InfoBeforeFile=assets\before_install.txt
; DisableDirPage intentionally left at its default (enabled) so the wizard's
; directory-selection page is shown, same as VS Code's installer.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\launcher.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\gui.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\tui.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\bootstrap.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

; subburn/ is a growing package (engines, routes, etc.) - bundled as a whole
; tree so new files under it never need an installer edit, same idea as the
; web\* entry below.
Source: "..\subburn\*"; DestDir: "{app}\subburn"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__"

Source: "..\web\*"; DestDir: "{app}\web"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "node_modules,.next,*.log"

Source: "runtimes\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "runtimes\node\*"; DestDir: "{app}\node"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "runtimes\ffmpeg\*"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Subtitle Burner"; Filename: "{app}\python\python.exe"; Parameters: """{app}\gui.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Subtitle Burner (Terminal UI)"; Filename: "{app}\python\python.exe"; Parameters: """{app}\tui.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Uninstall Subtitle Burner"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Subtitle Burner"; Filename: "{app}\python\python.exe"; Parameters: """{app}\gui.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\python.exe"; Parameters: """{app}\gui.py"""; WorkingDir: "{app}"; Description: "Launch Subtitle Burner now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Runtime-generated files/directories that Inno Setup didn't itself install,
; so its own uninstall log wouldn't otherwise know to remove them.
Type: filesandordirs; Name: "{app}\jobs"
Type: filesandordirs; Name: "{app}\web\node_modules"
Type: filesandordirs; Name: "{app}\web\.next"
Type: filesandordirs; Name: "{app}\python\Lib\site-packages"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\.bootstrap_complete"
