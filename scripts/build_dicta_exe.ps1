param(
    [switch]$SkipModels,
    [string]$PackageVersion = "1.1-pilot",
    [string]$DistRoot = "dist\Dicta"
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")

$repoRoot = (Resolve-Path -LiteralPath ".").Path
$repoDistRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot "dist"))
if ([System.IO.Path]::IsPathRooted($DistRoot)) {
    $dist = [System.IO.Path]::GetFullPath($DistRoot)
} else {
    $dist = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $DistRoot))
}

$comparison = [StringComparison]::OrdinalIgnoreCase
$repoDistRootTrimmed = $repoDistRoot.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)
$repoDistPrefix = $repoDistRootTrimmed + [System.IO.Path]::DirectorySeparatorChar
$distTrimmed = $dist.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)
if ($distTrimmed -eq $repoDistRootTrimmed -or -not $distTrimmed.StartsWith($repoDistPrefix, $comparison)) {
    throw "DistRoot must resolve to a package folder under $repoDistRoot."
}

function Clear-PackageDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $fullPathTrimmed = $fullPath.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    if ($fullPathTrimmed -eq $repoDistRootTrimmed -or -not $fullPathTrimmed.StartsWith($repoDistPrefix, $comparison)) {
        throw "Refusing to clear unsafe package path: $fullPath"
    }

    if (Test-Path -LiteralPath $fullPath) {
        $item = Get-Item -LiteralPath $fullPath
        if (-not $item.PSIsContainer) {
            throw "DistRoot must be a directory: $fullPath"
        }
        Get-ChildItem -LiteralPath $fullPath -Force | Remove-Item -Recurse -Force
    } else {
        New-Item -ItemType Directory -Force -Path $fullPath | Out-Null
    }
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

Invoke-NativeCommand -FilePath "python" -ArgumentList @("-m", "pip", "install", "-r", "requirements.txt")
Invoke-NativeCommand -FilePath "python" -ArgumentList @("-m", "pip", "install", "pyinstaller")
Invoke-NativeCommand -FilePath "python" -ArgumentList @("-m", "pip", "install", "pillow")
Invoke-NativeCommand -FilePath "python" -ArgumentList @("scripts\generate_app_icon.py")

$pyinstallerDistRoot = Join-Path $repoRoot "build\pyinstaller-dist"
$pyinstallerWorkRoot = Join-Path $repoRoot "build\pyinstaller-work"
$pyinstallerAppRoot = Join-Path $pyinstallerDistRoot "Dicta"
if (Test-Path -LiteralPath $pyinstallerAppRoot) {
    Remove-Item -LiteralPath $pyinstallerAppRoot -Recurse -Force
}
Invoke-NativeCommand -FilePath "python" -ArgumentList @(
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--distpath",
    $pyinstallerDistRoot,
    "--workpath",
    $pyinstallerWorkRoot,
    "--icon",
    "assets\app_icon.ico",
    "--name",
    "Dicta",
    "dicta.py"
)

if (-not (Test-Path -LiteralPath (Join-Path $pyinstallerAppRoot "Dicta.exe") -PathType Leaf)) {
    throw "PyInstaller did not create Dicta.exe in $pyinstallerAppRoot."
}

Clear-PackageDirectory -Path $dist
Get-ChildItem -LiteralPath $pyinstallerAppRoot -Force | Copy-Item -Destination $dist -Recurse -Force
New-Item -ItemType Directory -Force -Path "$dist\models", "$dist\.tools\whisper.cpp-build-compat\bin", "$dist\assets", "$dist\docs", "$dist\scripts", "$dist\translation" | Out-Null

if ($SkipModels) {
    @"
Dicta models are not included in this package.

Copy these files into this folder before using recognition:
- ggml-small-q5_1.bin
- ggml-large-v3-turbo-q5_0.bin

Supported models:
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
    $packageModels = @(
        "ggml-small-q5_1.bin",
        "ggml-small.bin",
        "ggml-medium-q5_0.bin",
        "ggml-medium.bin",
        "ggml-large-v3-turbo-q5_0.bin",
        "ggml-large-v3-turbo.bin"
    )

    $copiedModels = 0
    foreach ($modelName in $packageModels) {
        $modelPath = Join-Path "models" $modelName
        if (Test-Path -LiteralPath $modelPath -PathType Leaf) {
            Copy-Item -LiteralPath $modelPath -Destination "$dist\models" -Force
            $copiedModels++
        }
    }
    if ($copiedModels -eq 0) {
        throw "No supported Dicta model found in models. Use -SkipModels for a code-only package or copy at least one supported ggml-*.bin model."
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
