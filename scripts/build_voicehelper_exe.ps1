$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")

python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m pip install pillow
python scripts\generate_app_icon.py
python -m PyInstaller --noconfirm --clean --windowed --icon "assets\app_icon.ico" --name VoiceHelper voicehelper.py

$dist = "dist\VoiceHelper"
New-Item -ItemType Directory -Force -Path "$dist\models", "$dist\.tools\whisper.cpp-build-compat\bin", "$dist\assets", "$dist\docs", "$dist\scripts" | Out-Null

Copy-Item -LiteralPath `
    "models\ggml-tiny-q5_1.bin", `
    "models\ggml-base-q5_1.bin", `
    "models\ggml-small-q5_1.bin" `
    -Destination "$dist\models" `
    -Force

Copy-Item `
    -Path ".tools\whisper.cpp-build-compat\bin\*" `
    -Destination "$dist\.tools\whisper.cpp-build-compat\bin" `
    -Recurse `
    -Force

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
    "scripts\list_audio_devices.ps1", `
    "scripts\list_audio_devices.cmd", `
    "scripts\audit_voicehelper_network.ps1", `
    "scripts\audit_voicehelper_network.cmd" `
    -Destination "$dist\scripts" `
    -Force

& "$dist\VoiceHelper.exe" --self-test

Write-Host "Build ready: $((Resolve-Path $dist).Path)"
