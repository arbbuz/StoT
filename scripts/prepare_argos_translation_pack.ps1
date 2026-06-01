param(
    [string]$SourceVenv = "",
    [string]$SourcePackagesDir = "",
    [string[]]$ModelNames = @("translate-en_ru-1_9", "translate-ru_en-1_9"),
    [string]$Destination = "",
    [string]$WorkerBuildRoot = ""
)

$ErrorActionPreference = "Stop"

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $repoRoot.Path

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

if ([string]::IsNullOrWhiteSpace($SourceVenv)) {
    $SourceVenv = Join-Path $repoRoot.Path "artifacts\argos-spike\.venv"
}
if ([string]::IsNullOrWhiteSpace($SourcePackagesDir)) {
    $SourcePackagesDir = Join-Path $env:USERPROFILE ".local\share\argos-translate\packages"
}
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $repoRoot.Path ".tools\argos-translate"
}
if ([string]::IsNullOrWhiteSpace($WorkerBuildRoot)) {
    $WorkerBuildRoot = Join-Path $repoRoot.Path "artifacts\argos-worker-pyinstaller"
}

$sourceVenvPath = Resolve-Path -LiteralPath $SourceVenv
$sourcePackagesPath = Resolve-Path -LiteralPath $SourcePackagesDir
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
$repoRootWithSeparator = [System.IO.Path]::GetFullPath($repoRoot.Path)
if (-not $repoRootWithSeparator.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
    $repoRootWithSeparator += [System.IO.Path]::DirectorySeparatorChar
}

if (-not $destinationPath.StartsWith($repoRootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Destination must stay inside repository root: $destinationPath"
}

$sourcePython = Join-Path $sourceVenvPath.Path "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $sourcePython -PathType Leaf)) {
    throw "Source venv python.exe not found: $sourcePython"
}

$destinationPackages = Join-Path $destinationPath "packages"
$destinationWorker = Join-Path $destinationPath "argos_translate_worker.py"
$destinationWorkerBundle = Join-Path $destinationPath "argos-worker"
$destinationWorkerExe = Join-Path $destinationWorkerBundle "argos-worker.exe"
$sourceWorker = Join-Path $repoRoot.Path "scripts\argos_translate_worker.py"

$models = @()
foreach ($modelName in $ModelNames) {
    $sourceModel = Join-Path $sourcePackagesPath.Path $modelName
    $sourceMetadata = Join-Path $sourceModel "metadata.json"
    if (-not (Test-Path -LiteralPath $sourceMetadata -PathType Leaf)) {
        throw "Argos model metadata not found: $sourceMetadata"
    }

    $metadata = Get-Content -LiteralPath $sourceMetadata -Raw -Encoding UTF8 | ConvertFrom-Json
    if (
        -not (
            ($metadata.from_code -eq "en" -and $metadata.to_code -eq "ru") -or
            ($metadata.from_code -eq "ru" -and $metadata.to_code -eq "en")
        )
    ) {
        throw "Model $modelName is not an en<->ru translation model."
    }

    $models += [ordered]@{
        name = $modelName
        fromCode = $metadata.from_code
        toCode = $metadata.to_code
        source = $sourceModel
        destination = Join-Path $destinationPackages $modelName
    }
}

if (Test-Path -LiteralPath $destinationPath) {
    Remove-Item -LiteralPath $destinationPath -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $destinationPath, $destinationPackages | Out-Null

Write-Host "Preparing Argos translation pack"
Write-Host "Destination: $destinationPath"
Write-Host "Source venv: $($sourceVenvPath.Path)"
Write-Host "Models: $($ModelNames -join ', ')"
Write-Host ""

Write-Host "Building portable worker executable..."
Invoke-NativeCommand -FilePath $sourcePython -ArgumentList @("-m", "pip", "install", "pyinstaller")

$workerBuildRootPath = [System.IO.Path]::GetFullPath($WorkerBuildRoot)
$workerDist = Join-Path $workerBuildRootPath "dist"
$workerWork = Join-Path $workerBuildRootPath "build"
$workerSpec = Join-Path $workerBuildRootPath "spec"
if (Test-Path -LiteralPath $workerBuildRootPath) {
    Remove-Item -LiteralPath $workerBuildRootPath -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $workerDist, $workerWork, $workerSpec | Out-Null

$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--name", "argos-worker",
    "--distpath", $workerDist,
    "--workpath", $workerWork,
    "--specpath", $workerSpec,
    "--collect-all", "argostranslate",
    "--collect-all", "ctranslate2",
    "--collect-all", "sentencepiece",
    "--collect-all", "sacremoses",
    "--collect-all", "spacy",
    "--collect-all", "stanza",
    $sourceWorker
)
Invoke-NativeCommand -FilePath $sourcePython -ArgumentList $pyInstallerArgs

$builtWorkerBundle = Join-Path $workerDist "argos-worker"
$builtWorkerExe = Join-Path $builtWorkerBundle "argos-worker.exe"
if (-not (Test-Path -LiteralPath $builtWorkerExe -PathType Leaf)) {
    throw "Built worker executable not found: $builtWorkerExe"
}
Copy-Item -LiteralPath $builtWorkerBundle -Destination $destinationPath -Recurse -Force

Write-Host "Copying model packages..."
foreach ($model in $models) {
    New-Item -ItemType Directory -Force -Path $model.destination | Out-Null
    Copy-Item -Path (Join-Path $model.source "*") -Destination $model.destination -Recurse -Force
}

Write-Host "Copying worker..."
Copy-Item -LiteralPath $sourceWorker -Destination $destinationWorker -Force

Write-Host "Creating local data folders..."
New-Item -ItemType Directory -Force -Path `
    (Join-Path $destinationPath "data"), `
    (Join-Path $destinationPath "config"), `
    (Join-Path $destinationPath "cache") | Out-Null

$validationRequest = @{
    text = "test"
    from_code = "en"
    to_code = "ru"
    packages_dir = $destinationPackages
} | ConvertTo-Json -Compress
Write-Host "Validating portable worker..."
$validationProcessInfo = [System.Diagnostics.ProcessStartInfo]::new()
$validationProcessInfo.FileName = $destinationWorkerExe
$validationProcessInfo.UseShellExecute = $false
$validationProcessInfo.RedirectStandardInput = $true
$validationProcessInfo.RedirectStandardOutput = $true
$validationProcessInfo.RedirectStandardError = $true
$validationProcessInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
$validationProcessInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
$validationProcess = [System.Diagnostics.Process]::new()
$validationProcess.StartInfo = $validationProcessInfo
[void]$validationProcess.Start()
$validationStdoutTask = $validationProcess.StandardOutput.ReadToEndAsync()
$validationStderrTask = $validationProcess.StandardError.ReadToEndAsync()
$validationProcess.StandardInput.Write($validationRequest)
$validationProcess.StandardInput.Close()
if (-not $validationProcess.WaitForExit(120000)) {
    try {
        $validationProcess.Kill()
    } catch {
    }
    throw "Argos worker validation timed out."
}
$validationOutput = $validationStdoutTask.Result
$validationError = $validationStderrTask.Result
if ($validationProcess.ExitCode -ne 0 -or ($validationOutput -notmatch '"ok"\s*:\s*true')) {
    throw "Argos worker validation failed: stdout=$validationOutput stderr=$validationError"
}

$packManifest = [ordered]@{
    schemaVersion = 1
    packName = "Dicta Argos EN-RU/RU-EN Translation Pack"
    runtime = "argos-worker"
    worker = "argos_translate_worker.py"
    workerExe = "argos-worker\argos-worker.exe"
    packagesDir = "packages"
    models = @($models | ForEach-Object {
        [ordered]@{
            name = $_.name
            fromCode = $_.fromCode
            toCode = $_.toCode
            source = $_.source
        }
    })
    sourceVenv = $sourceVenvPath.Path
    generatedAtUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}
$packManifestPath = Join-Path $destinationPath "pack_manifest.json"
$packManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $packManifestPath -Encoding UTF8

Write-Host ""
Write-Host "Translation pack ready."
Write-Host "Manifest: $packManifestPath"
Write-Host "Runtime: $destinationWorkerExe"
foreach ($model in $models) {
    Write-Host "Model $($model.fromCode)->$($model.toCode): $($model.destination)"
}
