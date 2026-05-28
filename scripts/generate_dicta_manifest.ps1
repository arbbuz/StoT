param(
    [string]$Root = "",
    [string]$PackageVersion = "1.1-pilot",
    [string]$SourceCommit = "",
    [switch]$CodeOnly
)

$ErrorActionPreference = "Stop"

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

if ([string]::IsNullOrWhiteSpace($Root)) {
    $rootPath = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\dist\Dicta")
} else {
    $rootPath = Resolve-Path -LiteralPath $Root
}

$root = $rootPath.Path
$script:RootUri = [System.Uri]::new($root.TrimEnd("\") + "\")
$manifestPath = Join-Path $root "manifest.json"
$shaPath = Join-Path $root "SHA256SUMS.txt"

Remove-Item -LiteralPath $manifestPath, $shaPath -Force -ErrorAction SilentlyContinue

function Convert-ToPackagePath {
    param([string]$FullName)

    $fileUri = [System.Uri]::new($FullName)
    return [System.Uri]::UnescapeDataString($script:RootUri.MakeRelativeUri($fileUri).ToString())
}

function Get-PackageCategory {
    param([string]$RelativePath)

    if ($RelativePath -eq "Dicta.exe") { return "application" }
    if ($RelativePath -like "_internal/*") { return "runtime" }
    if ($RelativePath -like ".tools/argos-translate/*") { return "translation-runtime" }
    if ($RelativePath -like ".tools/*") { return "speech-backend" }
    if ($RelativePath -like "models/*.bin") { return "model" }
    if ($RelativePath -like "models/*") { return "model-placeholder" }
    if ($RelativePath -like "assets/*") { return "asset" }
    if ($RelativePath -like "translation/*") { return "translation-config" }
    if ($RelativePath -like "docs/*") { return "documentation" }
    if ($RelativePath -like "scripts/*") { return "support-script" }
    return "package-file"
}

$payloadFiles = Get-ChildItem -LiteralPath $root -Recurse -File |
    Where-Object {
        $relative = Convert-ToPackagePath -FullName $_.FullName
        $relative -ne "manifest.json" -and
        $relative -ne "SHA256SUMS.txt" -and
        $relative -notlike "diagnostics/*"
    } |
    Sort-Object @{ Expression = { Convert-ToPackagePath -FullName $_.FullName } }

$entries = @()
foreach ($file in $payloadFiles) {
    $relative = Convert-ToPackagePath -FullName $file.FullName
    $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
    $entries += [ordered]@{
        path = $relative
        sizeBytes = $file.Length
        sha256 = $hash.Hash.ToLowerInvariant()
        category = Get-PackageCategory -RelativePath $relative
    }
}

$manifest = [ordered]@{
    schemaVersion = 1
    packageName = "Dicta"
    packageVersion = $PackageVersion
    packageKind = if ($CodeOnly) { "code-only" } else { "local-with-models" }
    generatedAtUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    sourceCommit = $SourceCommit
    modelPolicy = if ($CodeOnly) {
        "Whisper model .bin files are intentionally excluded and must be copied manually into models next to Dicta.exe."
    } else {
        "Whisper model .bin files are included from the local build machine."
    }
    totals = [ordered]@{
        fileCount = $entries.Count
        totalBytes = ($payloadFiles | Measure-Object -Property Length -Sum).Sum
    }
    files = $entries
}

$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

$shaEntries = @($entries)
$manifestHash = Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256
$manifestItem = Get-Item -LiteralPath $manifestPath
$shaEntries += [ordered]@{
    path = "manifest.json"
    sizeBytes = $manifestItem.Length
    sha256 = $manifestHash.Hash.ToLowerInvariant()
    category = "package-metadata"
}

$shaLines = $shaEntries |
    Sort-Object path |
    ForEach-Object { "$($_.sha256)  $($_.path)" }
$shaLines | Set-Content -LiteralPath $shaPath -Encoding UTF8

Write-Host "Manifest written: $manifestPath"
Write-Host "SHA256SUMS written: $shaPath"
Write-Host "Files listed: $($shaEntries.Count)"
