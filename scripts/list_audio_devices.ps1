Write-Host "VoiceHelper audio devices"
Write-Host ""

$packageRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$program = Join-Path $packageRoot "VoiceHelper.exe"

if (-not (Test-Path -LiteralPath $program)) {
    Write-Host "[WARN] VoiceHelper.exe was not found next to scripts folder."
    Write-Host "       Fallback: checking with system Python, if available."
    python -c "import sounddevice as sd; print('default=', sd.default.device); print(sd.query_devices())"
    exit $LASTEXITCODE
}

$stdoutPath = Join-Path $env:TEMP "voicehelper_audio_devices_stdout.txt"
$stderrPath = Join-Path $env:TEMP "voicehelper_audio_devices_stderr.txt"
Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue

$process = Start-Process `
    -FilePath $program `
    -ArgumentList "--audio-devices" `
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

exit $process.ExitCode
