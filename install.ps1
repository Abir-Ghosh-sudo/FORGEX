#requires -Version 5.1
$ErrorActionPreference = "Stop"
$repo = "https://github.com/Abir-Ghosh-sudo/FORGEX/archive/refs/heads/main.zip"
$installRoot = Join-Path $env:LOCALAPPDATA "FORGEX"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("forgex-" + [guid]::NewGuid())
$zipPath = Join-Path $tempRoot "forgex.zip"
Write-Host "=== FORGEX Installer ===" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
try {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 --version *> $null
        if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ is required." }
        $pythonCommand = "py"
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python --version
        if ($LASTEXITCODE -ne 0) { throw "Could not run Python." }
        $pythonCommand = "python"
    } else { throw "Python 3.11+ is required. Install it from python.org." }
    Write-Host "Downloading FORGEX..."
    Invoke-WebRequest -Uri $repo -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $tempRoot -Force
    $source = Get-ChildItem -Path $tempRoot -Directory | Where-Object { $_.Name -like "FORGEX-*" } | Select-Object -First 1
    if (-not $source) { throw "Could not extract FORGEX source." }
    if (Test-Path $installRoot) { Remove-Item $installRoot -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    Get-ChildItem -Path $source.FullName -Force | Copy-Item -Destination $installRoot -Recurse -Force
    $venvPath = Join-Path $installRoot ".venv"
    if ($pythonCommand -eq "py") { & py -3.11 -m venv $venvPath } else { & python -m venv $venvPath }
    if ($LASTEXITCODE -ne 0) { throw "Failed to create Python virtual environment." }
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    Write-Host "Installing FORGEX dependencies..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
    & $venvPython -m pip install $installRoot
    if ($LASTEXITCODE -ne 0) { throw "FORGEX installation failed." }
    $binDir = Join-Path $installRoot "bin"
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    $shim = Join-Path $binDir "forgex.cmd"
    $shimContent = "@echo off" + [Environment]::NewLine + '"' + $venvPython + '" -m forgex.cli.app %*' + [Environment]::NewLine
    Set-Content -Path $shim -Value $shimContent -Encoding ASCII
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathParts = @($userPath -split ";" | Where-Object { $_ })
    if ($pathParts -notcontains $binDir) {
        [Environment]::SetEnvironmentVariable("Path", ((@($pathParts) + $binDir) -join ";"), "User")
    }
    $env:Path = "$binDir;$env:Path"
    & $shim --version
    if ($LASTEXITCODE -ne 0) { throw "FORGEX version check failed." }
    Write-Host "FORGEX installed successfully!" -ForegroundColor Green
    Write-Host "Run 'forgex doctor' or 'forgex chat' in a new terminal."
} finally {
    if (Test-Path $tempRoot) { Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
