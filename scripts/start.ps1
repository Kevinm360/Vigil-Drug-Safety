param([ValidateRange(1024,65535)][int]$Port = 8766, [switch]$Background)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    Write-Host 'Creating a Python virtual environment…'
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment setup failed. Use Python 3.12 or 3.13.' }
}
$pythonRequirementsHash = (Get-FileHash -LiteralPath 'config/requirements/local.txt' -Algorithm SHA256).Hash
$pythonMarker = Join-Path $projectRoot '.venv\requirements.sha256'
if (-not (Test-Path -LiteralPath $pythonMarker) -or (Get-Content -LiteralPath $pythonMarker -Raw).Trim() -ne $pythonRequirementsHash) {
    & $projectPython -m pip install -r config/requirements/local.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed. Re-running this launcher will retry.' }
    Set-Content -LiteralPath $pythonMarker -Value $pythonRequirementsHash
}
$nodeRequirementsHash = (Get-FileHash -LiteralPath 'package-lock.json' -Algorithm SHA256).Hash
$nodeMarker = Join-Path $projectRoot 'node_modules\.vigil-dependencies.sha256'
if (-not (Test-Path -LiteralPath $nodeMarker) -or (Get-Content -LiteralPath $nodeMarker -Raw).Trim() -ne $nodeRequirementsHash) {
    npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    Set-Content -LiteralPath $nodeMarker -Value $nodeRequirementsHash
}
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
Write-Host "Open http://127.0.0.1:$Port in your browser."
if ($Background) {
    $appUrl = "http://127.0.0.1:$Port"
    try {
        $existingApp = Invoke-RestMethod -Uri "$appUrl/api/health" -TimeoutSec 2
        if ($existingApp.service -eq 'Side Effects Signal Monitor' -and $existingApp.status -eq 'ok') {
            Write-Host "Vigil is already running at $appUrl"
            return
        }
        throw "Port $Port is already serving another application. Choose -Port with a different number."
    } catch {
        if ($_.Exception.Message -like '*already serving another*') { throw }
    }
    $runtimeDirectory = Join-Path $projectRoot '.vigil-runtime'
    New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
    $stdoutPath = Join-Path $runtimeDirectory 'server.log'
    $stderrPath = Join-Path $runtimeDirectory 'server-error.log'
    $serverProcess = Start-Process -FilePath $projectPython -ArgumentList @('backend/server.py', '--port', "$Port") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $serverReady = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $serverProcess.Refresh()
        if ($serverProcess.HasExited) { throw "The app did not start. See $stderrPath" }
        try {
            $health = Invoke-RestMethod -Uri "$appUrl/api/health" -TimeoutSec 2
            if ($health.status -eq 'ok' -and $health.service -eq 'Side Effects Signal Monitor') { $serverReady = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (-not $serverReady) {
        Stop-Process -Id $serverProcess.Id -ErrorAction SilentlyContinue
        throw "The app did not become ready. See $stderrPath"
    }
    @{pid=$serverProcess.Id; port=$Port; url=$appUrl; started_at=[DateTimeOffset]::Now.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDirectory 'server.json')
    Write-Host "Vigil is running at $appUrl. It will keep running when this terminal closes. Use .\scripts\stop.ps1 to stop it."
    return
}
Write-Host 'Press Ctrl+C to stop.'
& $projectPython backend/server.py --port $Port
