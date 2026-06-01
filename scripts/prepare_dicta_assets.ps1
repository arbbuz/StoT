param(
    [string]$WhisperCppVersion = "v1.8.4",
    [switch]$SkipModels,
    [switch]$IncludeQualityModels,
    [switch]$SkipVulkan,
    [switch]$RequireVulkan
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")

$compatBinDir = ".tools\whisper.cpp-build-compat\bin"
$avx2BinDir = ".tools\whisper.cpp-build-avx2\bin"
$sse42BinDir = ".tools\whisper.cpp-build-sse42\bin"
$vulkanBinDir = ".tools\whisper.cpp-build-vulkan\bin"
$modelsDir = "models"
New-Item -ItemType Directory -Force -Path $compatBinDir, $avx2BinDir, $sse42BinDir, $modelsDir | Out-Null

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

function Invoke-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "$FilePath $($ArgumentList -join ' ') failed with exit code $LASTEXITCODE"
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Add-LocalGeneratorArgs {
    param(
        [string[]]$ConfigureArgs
    )

    $localW64DevKit = Join-Path (Get-Location) ".tools\w64devkit\bin"
    if (Test-Path -LiteralPath (Join-Path $localW64DevKit "gcc.exe")) {
        $env:PATH = "$localW64DevKit;$env:PATH"
        return $ConfigureArgs + @("-G", "MinGW Makefiles", "-DCMAKE_BUILD_TYPE=Release")
    }
    if ($env:GITHUB_ACTIONS -eq "true") {
        return $ConfigureArgs + @("-G", "Visual Studio 17 2022", "-A", "x64")
    }
    return $ConfigureArgs
}

function Copy-BuiltWhisperBackend {
    param(
        [string]$BuildDir,
        [string]$Destination,
        [string]$Label
    )

    $builtCli = Get-ChildItem -LiteralPath $BuildDir -Recurse -Filter "whisper-cli.exe" | Select-Object -First 1
    if ($null -eq $builtCli) {
        throw "Built whisper-cli.exe was not found in $Label build output."
    }

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Remove-Item -Path (Join-Path $Destination "*") -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath $builtCli.FullName -Destination $Destination -Force

    Get-ChildItem -LiteralPath $BuildDir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -ieq ".dll" } |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $Destination -Force
        }
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

$configureArgs = Add-LocalGeneratorArgs -ConfigureArgs $configureArgs

Invoke-NativeCommand -FilePath $cmakeExe -ArgumentList $configureArgs

Invoke-NativeCommand -FilePath $cmakeExe -ArgumentList @("--build", $buildDir, "--config", "Release", "--target", "whisper-cli", "--parallel", "2")

Copy-BuiltWhisperBackend -BuildDir $buildDir -Destination $compatBinDir -Label "compat"
Write-Host "Prepared scalar compat whisper.cpp backend in $compatBinDir"

$sse42BuildDir = ".tools\whisper.cpp-build-sse42-cmake"
Remove-Item -LiteralPath $sse42BuildDir -Recurse -Force -ErrorAction SilentlyContinue

$sse42ConfigureArgs = @(
    "-S", $sourceDir.FullName,
    "-B", $sse42BuildDir,
    "-DGGML_NATIVE=OFF",
    "-DGGML_SSE42=ON",
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
$sse42ConfigureArgs = Add-LocalGeneratorArgs -ConfigureArgs $sse42ConfigureArgs

Invoke-NativeCommand -FilePath $cmakeExe -ArgumentList $sse42ConfigureArgs

Invoke-NativeCommand -FilePath $cmakeExe -ArgumentList @("--build", $sse42BuildDir, "--config", "Release", "--target", "whisper-cli", "--parallel", "2")

Copy-BuiltWhisperBackend -BuildDir $sse42BuildDir -Destination $sse42BinDir -Label "SSE4.2"
Write-Host "Prepared SSE4.2 whisper.cpp backend in $sse42BinDir"

if (-not $SkipVulkan) {
    $vulkanTool = Get-Command glslc -ErrorAction SilentlyContinue
    if ($env:VULKAN_SDK -or $vulkanTool) {
        $vulkanBuildDir = ".tools\whisper.cpp-build-vulkan-cmake"
        Remove-Item -LiteralPath $vulkanBuildDir -Recurse -Force -ErrorAction SilentlyContinue

        $vulkanConfigureArgs = @(
            "-S", $sourceDir.FullName,
            "-B", $vulkanBuildDir,
            "-DGGML_NATIVE=OFF",
            "-DGGML_VULKAN=ON",
            "-DWHISPER_BUILD_TESTS=OFF",
            "-DWHISPER_BUILD_SERVER=OFF",
            "-DWHISPER_SDL2=OFF",
            "-DWHISPER_CURL=OFF"
        )
        $vulkanConfigureArgs = Add-LocalGeneratorArgs -ConfigureArgs $vulkanConfigureArgs

        Invoke-NativeCommand -FilePath $cmakeExe -ArgumentList $vulkanConfigureArgs

        Invoke-NativeCommand -FilePath $cmakeExe -ArgumentList @("--build", $vulkanBuildDir, "--config", "Release", "--target", "whisper-cli", "--parallel", "2")

        Copy-BuiltWhisperBackend -BuildDir $vulkanBuildDir -Destination $vulkanBinDir -Label "Vulkan"
        Write-Host "Prepared Vulkan whisper.cpp backend in $vulkanBinDir"
    } elseif ($RequireVulkan) {
        throw "Vulkan build requested but Vulkan SDK/glslc was not found."
    } else {
        Write-Host "Skipping Vulkan backend build: Vulkan SDK/glslc was not found."
    }
}

if (-not $SkipModels) {
    $models = @(
        "ggml-small-q5_1.bin"
    )
    if ($IncludeQualityModels) {
        $models += @(
            "ggml-small.bin"
        )
    }

    foreach ($model in $models) {
        $url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$model"
        $destination = Join-Path $modelsDir $model
        Download-File -Url $url -Destination $destination
    }
} else {
    Write-Host "Skipping model downloads."
}

Write-Host "Dicta assets are ready."
