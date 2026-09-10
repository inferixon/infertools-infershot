$pidPath = Join-Path $PSScriptRoot 'infershot.pid'
if (-not (Test-Path -LiteralPath $pidPath)) {
    exit 0
}

$processId = [int](Get-Content -LiteralPath $pidPath -Raw)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if ($process -and ($process.ProcessName -in @('python', 'pythonw'))) {
    Stop-Process -Id $processId -Force
}
Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
