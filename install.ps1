#requires -Version 5.1
param([switch]$WithOllama)
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
        & python -c "import sys; raise SystemExit(sys.version_info < (3, 11))"
        if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ is required. Detected an older Python version." }
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
    if ($WithOllama) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw "winget is required for automatic Ollama installation. Install Ollama manually from https://ollama.com/download/windows, then run: ollama pull qwen2.5-coder:1.5b"
        }
        Write-Host "Installing Ollama..."
        winget install --id Ollama.Ollama --exact --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw "Ollama installation failed. Install it from https://ollama.com/download/windows and rerun: ollama pull qwen2.5-coder:1.5b" }
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        $ollama = Get-Command ollama -ErrorAction SilentlyContinue
        if (-not $ollama) {
            $candidate = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
            if (Test-Path $candidate) { $ollama = $candidate }
        }
        if (-not $ollama) { throw "Ollama installed. Open a new PowerShell window, then run: ollama pull qwen2.5-coder:1.5b" }
        Write-Host "Downloading the lightweight default coding model (qwen2.5-coder:1.5b)..."
        & $ollama.Source pull qwen2.5-coder:1.5b
        if ($LASTEXITCODE -ne 0) { throw "Ollama is installed, but the model download failed. Start Ollama and run: ollama pull qwen2.5-coder:1.5b" }
        & $shim model use ollama qwen2.5-coder:1.5b
        if ($LASTEXITCODE -ne 0) { throw "Model downloaded, but FORGEX could not select it. Run: forgex model use ollama qwen2.5-coder:1.5b" }
    }
    Write-Host "FORGEX installed successfully!" -ForegroundColor Green
    Write-Host "Run 'forgex doctor' then 'forgex chat' in a new terminal."
} finally {
    if (Test-Path $tempRoot) { Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
