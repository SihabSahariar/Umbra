# Builds a standalone Windows app into dist\Umbra\Umbra.exe
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1          # app only
#         powershell -ExecutionPolicy Bypass -File build.ps1 -Setup   # app + dist\Umbra-Setup.exe
param([switch]$Setup)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade pyinstaller | Out-Null

python -m PyInstaller main.py `
    --name Umbra `
    --icon "assets\umbra-brand\icons\umbra.ico" `
    --noconfirm `
    --windowed `
    --onedir `
    --add-data "assets;assets" `
    --collect-data mediapipe `
    --collect-binaries mediapipe `
    --exclude-module tensorflow `
    --exclude-module matplotlib
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "Built: dist\Umbra\Umbra.exe"

if ($Setup) {
    $iscc = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) not found - install it from https://jrsoftware.org/isinfo.php" }
    $version = python -c "import umbra; print(umbra.__version__)"
    & $iscc "/DAppVersion=$version" "installer\umbra.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "Built: dist\Umbra-Setup.exe (version $version)"
}
