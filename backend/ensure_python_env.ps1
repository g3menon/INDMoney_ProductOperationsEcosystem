# Ensures backend/.venv uses CPython 3.11.x and requirements are installed.
# Run from anywhere: pwsh -File backend/ensure_python_env.ps1
$ErrorActionPreference = 'Stop'
$BackendRoot = $PSScriptRoot
Push-Location $BackendRoot

function Test-Venv311 {
    param([string]$VenvPython)
    if (-not (Test-Path $VenvPython)) { return $false }
    $majmin = & $VenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    return ($majmin -eq '3.11')
}

$pyLauncherOk = $false
if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11)" 2>$null
    if ($LASTEXITCODE -eq 0) { $pyLauncherOk = $true }
}

if (-not $pyLauncherOk) {
    Write-Error @"
Python 3.11 was not found (try: py -3.11).

Install CPython 3.11.x (64-bit) from https://www.python.org/downloads/
or winget install Python.Python.3.11
"@
    exit 1
}

$venvPy = Join-Path $BackendRoot '.venv\Scripts\python.exe'
if (-not (Test-Venv311 -VenvPython $venvPy)) {
    Write-Host 'Creating backend\.venv with Python 3.11...'
    Remove-Item -Recurse -Force (Join-Path $BackendRoot '.venv') -ErrorAction SilentlyContinue
    & py -3.11 -m venv (Join-Path $BackendRoot '.venv')
    $venvPy = Join-Path $BackendRoot '.venv\Scripts\python.exe'
}

if (-not (Test-Venv311 -VenvPython $venvPy)) {
    Write-Error 'Failed to create a Python 3.11 virtual environment.'
    exit 1
}

& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r (Join-Path $BackendRoot 'requirements.txt')

$ver = & $venvPy -c "import sys; print(sys.version.split()[0])"
Write-Host "OK: backend venv Python $ver"
Write-Host "    Executable: $venvPy"

Pop-Location
