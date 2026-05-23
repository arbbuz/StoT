Write-Host "Dicta backend comparison"
Write-Host ""

$packageRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$program = Join-Path $packageRoot "Dicta.exe"
$arguments = @("--benchmark-backends", "--include-faster-whisper")

if (-not (Test-Path -LiteralPath $program)) {
    Write-Host "[WARN] Dicta.exe was not found next to scripts folder."
    Write-Host "       Fallback: checking with system Python, if available."
    python (Join-Path $packageRoot "dicta.py") @arguments
    exit $LASTEXITCODE
}

$stdoutPath = Join-Path $env:TEMP "dicta_backend_compare_stdout.txt"
$stderrPath = Join-Path $env:TEMP "dicta_backend_compare_stderr.txt"
Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue

$process = Start-Process `
    -FilePath $program `
    -ArgumentList $arguments `
    -Wait `
    -PassThru `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -WindowStyle Hidden

$ansi = [System.Text.Encoding]::GetEncoding([System.Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage)
$stdout = if (Test-Path -LiteralPath $stdoutPath) { [System.IO.File]::ReadAllText($stdoutPath, $ansi) } else { "" }
$stderr = if (Test-Path -LiteralPath $stderrPath) { [System.IO.File]::ReadAllText($stderrPath, $ansi) } else { "" }

if (-not [string]::IsNullOrWhiteSpace($stdout)) {
    Write-Host $stdout.TrimEnd()
}
if (-not [string]::IsNullOrWhiteSpace($stderr)) {
    Write-Host $stderr.TrimEnd()
}

exit $process.ExitCode
