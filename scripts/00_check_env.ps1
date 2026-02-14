Param(
    [switch]$PrintPythonPath
)

$ErrorActionPreference = "Stop"

function Test-PythonExe {
    Param(
        [string]$ExePath
    )
    if (-not $ExePath) {
        return $false
    }
    try {
        & $ExePath -c "import sys;print(sys.executable)" 1>$null 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Resolve-PythonExe {
    if ($env:PATENT_PYTHON -and (Test-Path $env:PATENT_PYTHON)) {
        if (Test-PythonExe -ExePath $env:PATENT_PYTHON) {
            return $env:PATENT_PYTHON
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and (Test-PythonExe -ExePath $pythonCmd.Source)) {
        return $pythonCmd.Source
    }

    $python3Cmd = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3Cmd -and (Test-PythonExe -ExePath $python3Cmd.Source)) {
        return $python3Cmd.Source
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            $pyExe = & $pyCmd.Source -3 -c "import sys;print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $pyExe -and (Test-PythonExe -ExePath $pyExe.Trim())) {
                return $pyExe.Trim()
            }
        } catch {
        }
    }

    $pipCmd = Get-Command pip -ErrorAction SilentlyContinue
    if ($pipCmd) {
        $pipDir = Split-Path -Parent $pipCmd.Source
        $pyNextToPip = Join-Path $pipDir "python.exe"
        if ((Test-Path $pyNextToPip) -and (Test-PythonExe -ExePath $pyNextToPip)) {
            return $pyNextToPip
        }
        $pyOneLevelUp = Join-Path (Split-Path -Parent $pipDir) "python.exe"
        if ((Test-Path $pyOneLevelUp) -and (Test-PythonExe -ExePath $pyOneLevelUp)) {
            return $pyOneLevelUp
        }
    }

    return $null
}

$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCmd) {
    throw "ERROR: git not found"
}

$pipCmd = Get-Command pip -ErrorAction SilentlyContinue
if (-not $pipCmd) {
    throw "ERROR: pip not found"
}

$pythonExe = Resolve-PythonExe
if (-not $pythonExe) {
    throw "ERROR: No runnable Python executable found. Set PATENT_PYTHON to a valid python.exe path."
}

$skillRoot = Split-Path -Parent $PSScriptRoot
$vendorPath = Join-Path $skillRoot ".vendor"
$docxImportCmd = "import sys; sys.path.insert(0, r'$vendorPath'); import docx"
$docxOk = $false
try {
    & $pythonExe -c $docxImportCmd 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        $docxOk = $true
    }
} catch {
}
if (-not $docxOk) {
    Write-Warning "python-docx not installed. Run: python -m pip install python-docx --target `"$skillRoot\\.vendor`""
}

if ($PrintPythonPath) {
    Write-Output $pythonExe
} else {
    Write-Output "OK"
    Write-Output "python_exe=$pythonExe"
}

exit 0
