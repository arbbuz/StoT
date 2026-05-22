param(
    [string]$ProgramPath = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProgramPath)) {
    $packageRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
    $ProgramPath = Join-Path $packageRoot "VoiceHelper.exe"
}

$resolved = Resolve-Path -LiteralPath $ProgramPath
$program = $resolved.Path

Write-Host "VoiceHelper Russian spellchecker check"
Write-Host "Program: $program"
Write-Host ""

$stdoutPath = Join-Path $env:TEMP "voicehelper_spellcheck_stdout.txt"
$stderrPath = Join-Path $env:TEMP "voicehelper_spellcheck_stderr.txt"
Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue

$process = Start-Process `
    -FilePath $program `
    -ArgumentList "--spell-test" `
    -Wait `
    -PassThru `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath

$ansi = [System.Text.Encoding]::GetEncoding([System.Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage)
$stdout = if (Test-Path -LiteralPath $stdoutPath) { [System.IO.File]::ReadAllText($stdoutPath, $ansi) } else { "" }
$stderr = if (Test-Path -LiteralPath $stderrPath) { [System.IO.File]::ReadAllText($stderrPath, $ansi) } else { "" }

if (-not [string]::IsNullOrWhiteSpace($stdout)) {
    Write-Host $stdout.TrimEnd()
}
if (-not [string]::IsNullOrWhiteSpace($stderr)) {
    Write-Host $stderr.TrimEnd()
}

$exitCode = $process.ExitCode

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "[OK] Russian Windows spellchecker is available for VoiceHelper."
    exit 0
}

Write-Host "[FAIL] Russian Windows spellchecker is unavailable or returned unexpected result."
Write-Host "       Check Windows language settings and install Russian typing/spelling components if required."
exit $exitCode
