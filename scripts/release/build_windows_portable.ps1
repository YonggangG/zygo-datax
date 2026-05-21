$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$Version = "0.1.0"
$AppName = "zygo-dataX"
$DistApp = Join-Path $Root "dist\zygo-dataX"
$ReleaseDir = Join-Path $Root "dist\release"
$PortableRoot = Join-Path $ReleaseDir "$AppName-$Version-portable"
$ZipPath = Join-Path $ReleaseDir "$AppName-$Version-portable.zip"

if (-not (Test-Path (Join-Path $DistApp "zygo-dataX.exe"))) {
  throw "Missing dist\zygo-dataX\zygo-dataX.exe. Run scripts\windows\build_windows_launcher.ps1 first."
}

if (Test-Path $PortableRoot) {
  Remove-Item $PortableRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PortableRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

Copy-Item -Path (Join-Path $DistApp "*") -Destination $PortableRoot -Recurse -Force
Copy-Item -Path (Join-Path $Root "packaging\windows\README-WINDOWS.txt") -Destination $PortableRoot -Force
Copy-Item -Path (Join-Path $Root "README.md") -Destination $PortableRoot -Force
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "runs") | Out-Null

if (Test-Path $ZipPath) {
  Remove-Item $ZipPath -Force
}
Compress-Archive -Path $PortableRoot -DestinationPath $ZipPath -Force

Write-Host "Portable package: $ZipPath"
