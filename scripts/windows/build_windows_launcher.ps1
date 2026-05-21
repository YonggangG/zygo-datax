$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3.10+ is required and must be available as python in PATH."
}

python -m venv .venv-win
& .\.venv-win\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-win\Scripts\python.exe -m pip install -e . pyinstaller

& .\.venv-win\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name zygo-dataX --collect-all h5py --collect-all matplotlib --collect-all numpy --hidden-import zygo_datax.web.app src\zygo_datax\gui\launcher.py

Write-Host "Built: $Root\dist\zygo-dataX\zygo-dataX.exe"
