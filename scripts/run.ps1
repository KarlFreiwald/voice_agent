param([switch]$Demo)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path '.venv/Scripts/python.exe')) { throw 'Run scripts/setup.ps1 first.' }
if ($Demo) { & ./.venv/Scripts/python.exe -m voice_agent --demo }
else { & ./.venv/Scripts/python.exe -m voice_agent }
exit $LASTEXITCODE
