param(
    [string]$SourceVenv = "",
    [string]$SourcePackagesDir = "",
    [string[]]$ModelNames = @("translate-en_ru-1_9", "translate-ru_en-1_9"),
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $repoRoot.Path

if ([string]::IsNullOrWhiteSpace($SourceVenv)) {
    $SourceVenv = Join-Path $repoRoot.Path "artifacts\argos-spike\.venv"
}
if ([string]::IsNullOrWhiteSpace($SourcePackagesDir)) {
    $SourcePackagesDir = Join-Path $env:USERPROFILE ".local\share\argos-translate\packages"
}
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $repoRoot.Path ".tools\argos-translate"
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

$destinationVenv = Join-Path $destinationPath ".venv"
$destinationPackages = Join-Path $destinationPath "packages"
$destinationWorker = Join-Path $destinationPath "argos_translate_worker.py"
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

New-Item -ItemType Directory -Force -Path $destinationPath, $destinationPackages | Out-Null

Write-Host "Preparing Argos translation pack"
Write-Host "Destination: $destinationPath"
Write-Host "Source venv: $($sourceVenvPath.Path)"
Write-Host "Models: $($ModelNames -join ', ')"
Write-Host ""

Write-Host "Copying runtime venv..."
New-Item -ItemType Directory -Force -Path $destinationVenv | Out-Null
Copy-Item -Path (Join-Path $sourceVenvPath.Path "*") -Destination $destinationVenv -Recurse -Force

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

$destinationPython = Join-Path $destinationVenv "Scripts\python.exe"
Write-Host "Validating runtime import..."
& $destinationPython -c "import argostranslate, ctranslate2; print('argos runtime ok')"
if ($LASTEXITCODE -ne 0) {
    throw "Argos runtime import check failed."
}

$packManifest = [ordered]@{
    schemaVersion = 1
    packName = "Dicta Argos EN-RU/RU-EN Translation Pack"
    runtime = ".venv"
    worker = "argos_translate_worker.py"
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
Write-Host "Runtime: $destinationPython"
foreach ($model in $models) {
    Write-Host "Model $($model.fromCode)->$($model.toCode): $($model.destination)"
}
