$ErrorActionPreference = 'Stop'
$statePath = Join-Path $PSScriptRoot '.vigil-runtime\server.json'
if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Host 'No background Vigil app is registered in this project.'
    return
}
$serverState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$vigilPid = [int]$serverState.pid
$vigilPort = [int]$serverState.port
if ($vigilPid -le 0 -or $vigilPort -lt 1024 -or $vigilPort -gt 65535) { throw 'The saved app state is invalid.' }
$serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $vigilPid"
if ($serverProcess) {
    $projectPython = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe')).Path
    if ($serverProcess.ExecutablePath -ne $projectPython -or $serverProcess.CommandLine -notmatch "backend[/\\]server\.py\s+--port\s+$vigilPort(?:\s|$)") {
        throw 'The saved process no longer belongs to this app. No process was stopped.'
    }
    Stop-Process -Id $vigilPid
    Write-Host "Stopped Vigil on port $vigilPort."
} else {
    Write-Host 'The background app has already stopped.'
}
Remove-Item -LiteralPath $statePath
