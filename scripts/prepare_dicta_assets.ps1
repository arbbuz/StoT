param(
    [string]$WhisperCppVersion = "v1.8.4",
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")

$compatBinDir = ".tools\whisper.cpp-build-compat\bin"
$avx2BinDir = ".tools\whisper.cpp-build-avx2\bin"
$modelsDir = "models"
New-Item -ItemType Directory -Force -Path $compatBinDir, $avx2BinDir, $modelsDir | Out-Null

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
$whisperExtract = Join-Path $env:TEMP "dicta-whisper-$WhisperCppVersion"
$whisperUrl = "https://github.com/ggml-org/whisper.cpp/releases/download/$WhisperCppVersion/whisper-bin-x64.zip"
$sourceZip = Join-Path $env:TEMP "whisper-src-$WhisperCppVersion.zip"
$sourceExtract = Join-Path $env:TEMP "dicta-whisper-src-$WhisperCppVersion"
$sourceUrl = "https://github.com/ggml-org/whisper.cpp/archive/refs/tags/$WhisperCppVersion.zip"

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

Remove-Item -Path (Join-Path $avx2BinDir "*") -Recurse -Force -ErrorAction SilentlyContinue
foreach ($fileName in $requiredReleaseFiles) {
    $source = Join-Path $releaseDir $fileName
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Required whisper.cpp release file was not found: $fileName"
    }
    Copy-Item -LiteralPath $source -Destination $avx2BinDir -Force
}
Write-Host "Prepared optional AVX2 whisper.cpp binaries in $avx2BinDir"

Download-File -Url $sourceUrl -Destination $sourceZip
Remove-Item -LiteralPath $sourceExtract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $sourceZip -DestinationPath $sourceExtract -Force

$sourceDir = Get-ChildItem -LiteralPath $sourceExtract -Directory | Select-Object -First 1
if ($null -eq $sourceDir) {
    throw "whisper.cpp source directory was not found after extraction."
}

$cmakeExe = $null
$localCmake = Join-Path (Get-Location) ".tools\cmake\bin\cmake.exe"
if (Test-Path -LiteralPath $localCmake) {
    $cmakeExe = $localCmake
} else {
    $cmakeCommand = Get-Command cmake -ErrorAction SilentlyContinue
    if ($cmakeCommand) {
        $cmakeExe = $cmakeCommand.Source
    }
}
if (-not $cmakeExe) {
    throw "cmake was not found. Install CMake or prepare .tools\cmake."
}

$buildDir = ".tools\whisper.cpp-build-compat-cmake"
Remove-Item -LiteralPath $buildDir -Recurse -Force -ErrorAction SilentlyContinue

$configureArgs = @(
    "-S", $sourceDir.FullName,
    "-B", $buildDir,
    "-DGGML_NATIVE=OFF",
    "-DGGML_SSE42=OFF",
    "-DGGML_AVX=OFF",
    "-DGGML_AVX2=OFF",
    "-DGGML_BMI2=OFF",
    "-DGGML_FMA=OFF",
    "-DGGML_F16C=OFF",
    "-DGGML_OPENMP=OFF",
    "-DWHISPER_BUILD_TESTS=OFF",
    "-DWHISPER_BUILD_SERVER=OFF",
    "-DWHISPER_SDL2=OFF",
    "-DWHISPER_CURL=OFF"
)

$localW64DevKit = Join-Path (Get-Location) ".tools\w64devkit\bin"
if (Test-Path -LiteralPath (Join-Path $localW64DevKit "gcc.exe")) {
    $env:PATH = "$localW64DevKit;$env:PATH"
    $configureArgs += @("-G", "MinGW Makefiles", "-DCMAKE_BUILD_TYPE=Release")
} elseif ($env:GITHUB_ACTIONS -eq "true") {
    $configureArgs += @("-G", "Visual Studio 17 2022", "-A", "x64")
}

& $cmakeExe @configureArgs
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure whisper.cpp compat build."
}

& $cmakeExe --build $buildDir --config Release --target whisper-cli --parallel 2
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build whisper.cpp compat backend."
}

$builtCli = Get-ChildItem -LiteralPath $buildDir -Recurse -Filter "whisper-cli.exe" | Select-Object -First 1
if ($null -eq $builtCli) {
    throw "Built whisper-cli.exe was not found in compat build output."
}

Remove-Item -Path (Join-Path $compatBinDir "*") -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $builtCli.FullName -Destination $compatBinDir -Force

$runtimeDllNames = @("whisper.dll", "ggml.dll", "ggml-base.dll", "ggml-cpu.dll", "libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll")
$runtimeDlls = Get-ChildItem -LiteralPath $buildDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $runtimeDllNames -contains $_.Name }
foreach ($dll in $runtimeDlls) {
    Copy-Item -LiteralPath $dll.FullName -Destination $compatBinDir -Force
}
Write-Host "Prepared scalar compat whisper.cpp backend in $compatBinDir"

if (-not $SkipModels) {
    $models = @(
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

Write-Host "Dicta assets are ready."
