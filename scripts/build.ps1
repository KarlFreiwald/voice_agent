$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
& ./.venv/Scripts/python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; build stopped.' }
& ./.venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name VoiceAgent desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Copy-Item -LiteralPath config.example.json -Destination dist/VoiceAgent/config.example.json
Write-Host 'Built dist/VoiceAgent/VoiceAgent.exe. Copy the entire VoiceAgent folder to distribute.'
Write-Host 'Create config.local.json beside the executable and add keys locally; never distribute credentials.'
