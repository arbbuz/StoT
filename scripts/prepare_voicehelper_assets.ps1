param(
    [string]$WhisperCppVersion = "v1.8.4",
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")

$whisperBinDir = ".tools\whisper.cpp-build-compat\bin"
$modelsDir = "models"
New-Item -ItemType Directory -Force -Path $whisperBinDir, $modelsDir | Out-Null

function Download-File {
    param(
        [string]$Url,
        [string]$Destination
    )

    if (Test-Path -LiteralPath $Destination) {
        $item = Get-Item -LiteralPath $Destination
        if ($item.Length -gt 0) {
            Write-Host "Already exists: $Destination ($([math]::Round($item.Length / 1MB, 2)) MB)"
            return
        }
    }

    Write-Host "Downloading: $Url"
    $tempPath = "$Destination.download"
    Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -Uri $Url -OutFile $tempPath -UseBasicParsing
    Move-Item -LiteralPath $tempPath -Destination $Destination -Force
}

$whisperZip = Join-Path $env:TEMP "whisper-bin-x64-$WhisperCppVersion.zip"
$whisperExtract = Join-Path $env:TEMP "voicehelper-whisper-$WhisperCppVersion"
$whisperUrl = "https://github.com/ggml-org/whisper.cpp/releases/download/$WhisperCppVersion/whisper-bin-x64.zip"

Download-File -Url $whisperUrl -Destination $whisperZip
Remove-Item -LiteralPath $whisperExtract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $whisperZip -DestinationPath $whisperExtract -Force

$releaseDir = Join-Path $whisperExtract "Release"
if (-not (Test-Path -LiteralPath (Join-Path $releaseDir "whisper-cli.exe"))) {
    throw "whisper-cli.exe was not found in downloaded whisper.cpp release."
}

$requiredReleaseFiles = @(
    "whisper-cli.exe",
    "whisper.dll",
    "ggml.dll",
    "ggml-base.dll",
    "ggml-cpu.dll"
)

Remove-Item -Path (Join-Path $whisperBinDir "*") -Recurse -Force -ErrorAction SilentlyContinue
foreach ($fileName in $requiredReleaseFiles) {
    $source = Join-Path $releaseDir $fileName
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required whisper.cpp release file was not found: $fileName"
    }
    Copy-Item -LiteralPath $source -Destination $whisperBinDir -Force
}
Write-Host "Prepared whisper.cpp binaries in $whisperBinDir"

if (-not $SkipModels) {
    $models = @(
        "ggml-tiny-q5_1.bin",
        "ggml-base-q5_1.bin",
        "ggml-small-q5_1.bin"
    )

    foreach ($model in $models) {
        $url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$model"
        $destination = Join-Path $modelsDir $model
        Download-File -Url $url -Destination $destination
    }
} else {
    Write-Host "Skipping model downloads."
}

Write-Host "VoiceHelper assets are ready."
