$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = ".\.venv\Scripts\python.exe"

if (-not (Test-Path ".\.env")) {
    if (Test-Path ".\.env.example") {
        Copy-Item ".\.env.example" ".\.env"
    }

    throw @"
Falta configurar .env en la raiz de DMS_API_SERVER.
Se creo .env desde .env.example si el archivo de ejemplo estaba disponible.
Edita .env con las credenciales reales de MySQL y vuelve a ejecutar:
  notepad .env
  .\scripts\start.ps1
"@
}

function Resolve-Python {
    if ($env:PYTHON_EXE -and (Test-Path $env:PYTHON_EXE)) {
        return @($env:PYTHON_EXE)
    }

    $candidates = @(
        @("py", "-3.13"),
        @("py", "-3"),
        @("python"),
        @("python3")
    )

    foreach ($candidate in $candidates) {
        $command = $candidate[0]
        $args = @()
        if ($candidate.Count -gt 1) {
            $args = $candidate[1..($candidate.Count - 1)]
        }

        try {
            & $command @args -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
            continue
        }
    }

    throw @"
No se encontro Python 3.11+ en este servidor.
Instala Python y vuelve a ejecutar este script.

Opciones:
  winget install -e --id Python.Python.3.13
  winget install -e --id Python.Python.3.12

Tambien puedes definir PYTHON_EXE con la ruta completa:
  `$env:PYTHON_EXE='C:\Path\To\python.exe'
"@
}

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    $python = @(Resolve-Python)
    $pythonCommand = $python[0]
    $pythonArgs = @()
    if ($python.Count -gt 1) {
        $pythonArgs = $python[1..($python.Count - 1)]
    }
    & $pythonCommand @pythonArgs -m venv .venv
}

if (-not (Test-Path $venvPython)) {
    throw "No se pudo crear el entorno virtual en .venv"
}

& $venvPython -m pip install -r requirements.txt
& $venvPython run.py
