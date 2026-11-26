param([Parameter(Mandatory=$true)][string]$DevkitPro,[Parameter(Mandatory=$true)][string]$Citro3D,[Parameter(Mandatory=$true)][string]$OutDir)
$ErrorActionPreference = 'Stop'
python -B (Join-Path (Split-Path -Parent $PSScriptRoot) 'playable_build.py') --devkitpro $DevkitPro --citro3d $Citro3D --out $OutDir
if ($LASTEXITCODE -ne 0) { throw 'Source build failed' }
