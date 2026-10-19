$ErrorActionPreference = 'Stop'
$sessionId = (Get-Process -Id $PID).SessionId
$scriptPath = Join-Path $PSScriptRoot 'infershot.py'
$pattern = '(?i)(?:^|[\s"])' + [regex]::Escape($scriptPath) + '(?:"|\s|$)'
$processes = @(Get-CimInstance Win32_Process | Where-Object {
    $_.SessionId -eq $sessionId -and $_.Name -in @('python.exe', 'pythonw.exe') -and
    $_.CommandLine -match $pattern
})
foreach ($process in $processes) {
    Stop-Process -Id $process.ProcessId -ErrorAction Stop
}
$pidPath = Join-Path $env:LOCALAPPDATA "Infershot\sessions\$sessionId\infershot.pid"
if (Test-Path -LiteralPath $pidPath) {
    $recordedId = (Get-Content -LiteralPath $pidPath -Raw).Trim()
    $recordedProcess = Get-Process -Id ([int]$recordedId) -ErrorAction SilentlyContinue
    if (-not $recordedProcess) {
        Remove-Item -LiteralPath $pidPath
    }
}
