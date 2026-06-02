param(
    [switch]$SkipModels,
    [string]$PackageVersion = "1.1-pilot"
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")

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

Invoke-NativeCommand -FilePath "python" -ArgumentList @("-m", "pip", "install", "-r", "requirements.txt")
Invoke-NativeCommand -FilePath "python" -ArgumentList @("-m", "pip", "install", "pyinstaller")
Invoke-NativeCommand -FilePath "python" -ArgumentList @("-m", "pip", "install", "pillow")
Invoke-NativeCommand -FilePath "python" -ArgumentList @("scripts\generate_app_icon.py")
Invoke-NativeCommand -FilePath "python" -ArgumentList @("-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--icon", "assets\app_icon.ico", "--name", "Dicta", "dicta.py")

$dist = "dist\Dicta"
New-Item -ItemType Directory -Force -Path "$dist\models", "$dist\.tools\whisper.cpp-build-compat\bin", "$dist\assets", "$dist\docs", "$dist\scripts", "$dist\translation" | Out-Null

if ($SkipModels) {
    @"
Dicta models are not included in this package.

Copy these files into this folder before using recognition:
- ggml-small-q5_1.bin

Optional higher-quality models:
- ggml-small.bin
- ggml-medium-q5_0.bin
- ggml-medium.bin
- ggml-large-v3-turbo-q5_0.bin
- ggml-large-v3-turbo.bin

Local source folder:
models\

Official upstream model source:
https://huggingface.co/ggerganov/whisper.cpp
"@ | Set-Content -LiteralPath "$dist\models\README_MODELS.txt" -Encoding UTF8
} else {
    $requiredModels = @("ggml-small-q5_1.bin")
    $optionalModels = @(
        "ggml-small.bin",
        "ggml-medium-q5_0.bin",
        "ggml-medium.bin",
        "ggml-large-v3-turbo-q5_0.bin",
        "ggml-large-v3-turbo.bin"
    )

    foreach ($modelName in $requiredModels) {
        Copy-Item -LiteralPath (Join-Path "models" $modelName) -Destination "$dist\models" -Force
    }

    foreach ($modelName in $optionalModels) {
        $modelPath = Join-Path "models" $modelName
        if (Test-Path -LiteralPath $modelPath -PathType Leaf) {
            Copy-Item -LiteralPath $modelPath -Destination "$dist\models" -Force
        }
    }
}

Copy-Item `
    -Path ".tools\whisper.cpp-build-compat\bin\*" `
    -Destination "$dist\.tools\whisper.cpp-build-compat\bin" `
    -Recurse `
    -Force

$avx2Source = ".tools\whisper.cpp-build-avx2\bin"
if (Test-Path -LiteralPath (Join-Path $avx2Source "whisper-cli.exe")) {
    New-Item -ItemType Directory -Force -Path "$dist\.tools\whisper.cpp-build-avx2\bin" | Out-Null
    foreach ($fileName in @("whisper-cli.exe", "whisper.dll", "ggml.dll", "ggml-base.dll", "ggml-cpu.dll")) {
        $source = Join-Path $avx2Source $fileName
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination "$dist\.tools\whisper.cpp-build-avx2\bin" -Force
        }
    }
}

$sse42Source = ".tools\whisper.cpp-build-sse42\bin"
if (Test-Path -LiteralPath (Join-Path $sse42Source "whisper-cli.exe")) {
    $sse42Destination = "$dist\.tools\whisper.cpp-build-sse42\bin"
    New-Item -ItemType Directory -Force -Path $sse42Destination | Out-Null
    Copy-Item -Path (Join-Path $sse42Source "*") -Destination $sse42Destination -Recurse -Force
}

foreach ($backend in @("vulkan", "cuda", "openvino")) {
    $backendSource = ".tools\whisper.cpp-build-$backend\bin"
    if (Test-Path -LiteralPath (Join-Path $backendSource "whisper-cli.exe")) {
        $backendDestination = "$dist\.tools\whisper.cpp-build-$backend\bin"
        New-Item -ItemType Directory -Force -Path $backendDestination | Out-Null
        Copy-Item -Path (Join-Path $backendSource "*") -Destination $backendDestination -Recurse -Force
    }
}

$argosSource = ".tools\argos-translate"
if (Test-Path -LiteralPath (Join-Path $argosSource "pack_manifest.json")) {
    $argosDestination = "$dist\.tools\argos-translate"
    New-Item -ItemType Directory -Force -Path $argosDestination | Out-Null
    Copy-Item -Path (Join-Path $argosSource "*") -Destination $argosDestination -Recurse -Force
}

Copy-Item -LiteralPath `
    "assets\app_icon.ico", `
    "assets\app_icon.png" `
    -Destination "$dist\assets" `
    -Force

Copy-Item -LiteralPath `
    "translation\glossary_en_ru.json" `
    -Destination "$dist\translation" `
    -Force

Copy-Item -LiteralPath `
    "dicta_dictionary_ru.json" `
    -Destination $dist `
    -Force

Copy-Item -LiteralPath `
    "docs\IB_PACKAGE_DESCRIPTION.md", `
    "docs\PROGRAM_LOGIC.md", `
    "docs\ROADMAP.md", `
    "docs\STAGE_0_2_1_MICROPHONE.md", `
    "docs\STAGE_0_2_2_DIAGNOSTICS.md", `
    "docs\STAGE_0_2_3_ERROR_MESSAGES.md", `
    "docs\STAGE_0_3_SPEED.md", `
    "docs\STAGE_0_4_CONVENIENCE.md", `
    "docs\STAGE_0_5_PERFORMANCE.md", `
    "docs\STAGE_1_0_CORPORATE_PILOT.md", `
    "docs\STAGE_1_1_BACKEND_THREADS.md", `
    "docs\UPDATE_PROCEDURE.md", `
    "docs\USER_CHECKLIST.md" `
    -Destination "$dist\docs" `
    -Force

Copy-Item -LiteralPath `
    "scripts\check_firewall_block.ps1", `
    "scripts\check_firewall_block.cmd", `
    "scripts\check_dicta_security.ps1", `
    "scripts\check_dicta_security.cmd", `
    "scripts\check_russian_spellcheck.ps1", `
    "scripts\check_russian_spellcheck.cmd", `
    "scripts\diagnose_dicta.ps1", `
    "scripts\diagnose_dicta.cmd", `
    "scripts\generate_dicta_manifest.ps1", `
    "scripts\verify_dicta_package.ps1", `
    "scripts\verify_dicta_package.cmd", `
    "scripts\benchmark_dicta_models.ps1", `
    "scripts\benchmark_dicta_models.cmd", `
    "scripts\compare_dicta_backends.ps1", `
    "scripts\compare_dicta_backends.cmd", `
    "scripts\list_audio_devices.ps1", `
    "scripts\list_audio_devices.cmd", `
    "scripts\audit_dicta_network.ps1", `
    "scripts\audit_dicta_network.cmd", `
    "scripts\argos_translate_worker.py", `
    "scripts\prepare_argos_translation_pack.ps1" `
    -Destination "$dist\scripts" `
    -Force

$sourceCommit = ""
try {
    $sourceCommit = (git rev-parse HEAD 2>$null).Trim()
} catch {
    $sourceCommit = ""
}

& ".\scripts\generate_dicta_manifest.ps1" `
    -Root $dist `
    -PackageVersion $PackageVersion `
    -SourceCommit $sourceCommit `
    -CodeOnly:$SkipModels

& "$dist\scripts\verify_dicta_package.ps1" -Root $dist

if ($SkipModels) {
    Invoke-NativeCommand -FilePath "$dist\Dicta.exe" -ArgumentList @("--self-test", "--allow-missing-models")
} else {
    Invoke-NativeCommand -FilePath "$dist\Dicta.exe" -ArgumentList @("--self-test")
}

Write-Host "Build ready: $((Resolve-Path $dist).Path)"
