$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 or newer (64-bit) and try again.' }
}
& ./.venv/Scripts/python.exe -m pip install -e '.[build]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check internet access and Python version.' }
if (-not (Test-Path 'config.local.json')) {
    Copy-Item -LiteralPath config.example.json -Destination config.local.json
}
Write-Host 'Setup complete. Add your keys to config.local.json, or start with demo mode.'
