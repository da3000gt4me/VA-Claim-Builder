$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $ProjectRoot

Write-Host "Building VA Claim Builder from: $ProjectRoot"
if (-not (Test-Path "$ProjectRoot\desktop_launcher.py")) {
    throw "desktop_launcher.py was not found at $ProjectRoot. Re-extract the complete build kit and run this script from packaging\windows."
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
Write-Host "Building normal Windows application..."
python -m PyInstaller --noconfirm --clean packaging\VAClaimBuilder.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller normal build failed with exit code $LASTEXITCODE. Review the console output above." }

$PortableExe = Join-Path $ProjectRoot "dist\VAClaimBuilder\VAClaimBuilder.exe"
if (-not (Test-Path -LiteralPath $PortableExe)) {
    throw "PyInstaller reported success, but the expected application was not created at: $PortableExe"
}
Write-Host "Portable application verified: $PortableExe"

Write-Host "Building diagnostic Windows application..."
python -m PyInstaller --noconfirm --clean packaging\VAClaimBuilder-Debug.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller diagnostic build failed with exit code $LASTEXITCODE. Review the console output above." }

$DebugExe = Join-Path $ProjectRoot "dist\VAClaimBuilder-Debug\VAClaimBuilder-Debug.exe"
if (-not (Test-Path -LiteralPath $DebugExe)) {
    throw "PyInstaller reported success, but the expected diagnostic application was not created at: $DebugExe"
}
Write-Host "Diagnostic application verified: $DebugExe"

# Locate the Inno Setup command-line compiler. Supports PATH, machine-wide,
# per-user, registry, custom install locations, and an explicit ISCC_PATH override.
$IsccCandidates = New-Object System.Collections.Generic.List[string]

function Add-IsccCandidate([string]$Path) {
    if ($Path -and (Test-Path -LiteralPath $Path)) {
        $Resolved = (Resolve-Path -LiteralPath $Path).Path
        if (-not $IsccCandidates.Contains($Resolved)) {
            $IsccCandidates.Add($Resolved)
        }
    }
}

# Explicit override, useful for custom/manual installations.
Add-IsccCandidate $env:ISCC_PATH

# Compiler available on PATH.
$PathCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($PathCommand) { Add-IsccCandidate $PathCommand.Source }

# Common machine-wide and per-user locations.
Add-IsccCandidate "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe"
Add-IsccCandidate "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
Add-IsccCandidate "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
Add-IsccCandidate "$env:LOCALAPPDATA\Inno Setup 6\ISCC.exe"

# Registry discovery for both 32-bit and 64-bit uninstall entries.
$RegistryKeys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'
)
foreach ($Key in $RegistryKeys) {
    if (Test-Path $Key) {
        $InstallLocation = (Get-ItemProperty -Path $Key -ErrorAction SilentlyContinue).InstallLocation
        if ($InstallLocation) { Add-IsccCandidate (Join-Path $InstallLocation 'ISCC.exe') }
    }
}

# Last-resort shallow search in likely roots, including custom subfolders.
$SearchRoots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "$env:LOCALAPPDATA\Programs") |
    Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
foreach ($Root in $SearchRoots) {
    Get-ChildItem -Path $Root -Filter ISCC.exe -File -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 5 |
        ForEach-Object { Add-IsccCandidate $_.FullName }
}

if ($IsccCandidates.Count -gt 0) {
    $PortableDir = Join-Path $ProjectRoot "dist\VAClaimBuilder"
    if (-not (Test-Path -LiteralPath $PortableDir) -or -not (Get-ChildItem -LiteralPath $PortableDir -Force -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "Installer build blocked because dist\VAClaimBuilder is missing or empty. The portable PyInstaller build must succeed first."
    }
    $Iscc = $IsccCandidates[0]
    Write-Host "Using Inno Setup compiler: $Iscc"
    & $Iscc packaging\windows\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed with exit code $LASTEXITCODE." }
    Write-Host "Installer created under packaging\windows\dist-installer."
} else {
    Write-Warning @"
Inno Setup compiler (ISCC.exe) was not found. The portable application was still created at:
  dist\VAClaimBuilder\VAClaimBuilder.exe

Confirm that you installed 'Inno Setup 6' rather than a similarly named builder/editor.
To locate it manually, run:
  Get-ChildItem 'C:\' -Filter ISCC.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 10 FullName

Then rerun this build with the discovered path:
  `$env:ISCC_PATH='C:\full\path\to\ISCC.exe'
  powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
"@
}

