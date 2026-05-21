$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$Inno = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $Inno) {
  $DefaultInno = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  if (Test-Path $DefaultInno) {
    $Inno = Get-Item $DefaultInno
  }
}

if (-not $Inno) {
  throw "Inno Setup 6 is required. Install it from https://jrsoftware.org/isinfo.php and ensure ISCC.exe is in PATH."
}

if (-not (Test-Path "dist\zygo-dataX\zygo-dataX.exe")) {
  throw "Missing dist\zygo-dataX\zygo-dataX.exe. Run scripts\windows\build_windows_launcher.ps1 first."
}

& $Inno.Source "packaging\windows\zygo-dataX.iss"

Write-Host "Installer output folder: dist\installer"
