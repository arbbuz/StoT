param(
    [switch]$SkipModels,
    [string]$PackageVersion = "1.0-pilot"
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")

python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m pip install pillow
python scripts\generate_app_icon.py
python -m PyInstaller --noconfirm --clean --windowed --icon "assets\app_icon.ico" --name VoiceHelper voicehelper.py

$dist = "dist\VoiceHelper"
New-Item -ItemType Directory -Force -Path "$dist\models", "$dist\.tools\whisper.cpp-build-compat\bin", "$dist\assets", "$dist\docs", "$dist\scripts" | Out-Null

if ($SkipModels) {
    @"
VoiceHelper models are not included in this package.

Copy these files into this folder before using recognition:
- ggml-tiny-q5_1.bin
- ggml-base-q5_1.bin
- ggml-small-q5_1.bin

Local source folder:
models\

Official upstream model source:
https://huggingface.co/ggerganov/whisper.cpp
"@ | Set-Content -LiteralPath "$dist\models\README_MODELS.txt" -Encoding UTF8
} else {
    Copy-Item -LiteralPath `
        "models\ggml-tiny-q5_1.bin", `
        "models\ggml-base-q5_1.bin", `
        "models\ggml-small-q5_1.bin" `
        -Destination "$dist\models" `
        -Force
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

foreach ($backend in @("vulkan", "cuda", "openvino")) {
    $backendSource = ".tools\whisper.cpp-build-$backend\bin"
    if (Test-Path -LiteralPath (Join-Path $backendSource "whisper-cli.exe")) {
        $backendDestination = "$dist\.tools\whisper.cpp-build-$backend\bin"
        New-Item -ItemType Directory -Force -Path $backendDestination | Out-Null
        Copy-Item -Path (Join-Path $backendSource "*") -Destination $backendDestination -Recurse -Force
    }
}

Copy-Item -LiteralPath `
    "assets\app_icon.ico", `
    "assets\app_icon.png" `
    -Destination "$dist\assets" `
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
    "docs\UPDATE_PROCEDURE.md", `
    "docs\USER_CHECKLIST.md" `
    -Destination "$dist\docs" `
    -Force

Copy-Item -LiteralPath `
    "scripts\check_firewall_block.ps1", `
    "scripts\check_firewall_block.cmd", `
    "scripts\check_voicehelper_security.ps1", `
    "scripts\check_voicehelper_security.cmd", `
    "scripts\check_russian_spellcheck.ps1", `
    "scripts\check_russian_spellcheck.cmd", `
    "scripts\diagnose_voicehelper.ps1", `
    "scripts\diagnose_voicehelper.cmd", `
    "scripts\generate_voicehelper_manifest.ps1", `
    "scripts\verify_voicehelper_package.ps1", `
    "scripts\verify_voicehelper_package.cmd", `
    "scripts\benchmark_voicehelper_models.ps1", `
    "scripts\benchmark_voicehelper_models.cmd", `
    "scripts\compare_voicehelper_backends.ps1", `
    "scripts\compare_voicehelper_backends.cmd", `
    "scripts\list_audio_devices.ps1", `
    "scripts\list_audio_devices.cmd", `
    "scripts\audit_voicehelper_network.ps1", `
    "scripts\audit_voicehelper_network.cmd" `
    -Destination "$dist\scripts" `
    -Force

$sourceCommit = ""
try {
    $sourceCommit = (git rev-parse HEAD 2>$null).Trim()
} catch {
    $sourceCommit = ""
}

& ".\scripts\generate_voicehelper_manifest.ps1" `
    -Root $dist `
    -PackageVersion $PackageVersion `
    -SourceCommit $sourceCommit `
    -CodeOnly:$SkipModels

& "$dist\scripts\verify_voicehelper_package.ps1" -Root $dist

if ($SkipModels) {
    & "$dist\VoiceHelper.exe" --self-test --allow-missing-models
} else {
    & "$dist\VoiceHelper.exe" --self-test
}

Write-Host "Build ready: $((Resolve-Path $dist).Path)"
