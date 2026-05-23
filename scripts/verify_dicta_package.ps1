param(
    [string]$Root = ""
)

$ErrorActionPreference = "Stop"

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

if ([string]::IsNullOrWhiteSpace($Root)) {
    $rootPath = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
} else {
    $rootPath = Resolve-Path -LiteralPath $Root
}

$root = $rootPath.Path
$rootWithSeparator = [System.IO.Path]::GetFullPath($root)
if (-not $rootWithSeparator.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
    $rootWithSeparator += [System.IO.Path]::DirectorySeparatorChar
}
$script:RootUri = [System.Uri]::new($rootWithSeparator)
$manifestPath = Join-Path $root "manifest.json"
$shaPath = Join-Path $root "SHA256SUMS.txt"
$failures = 0
$warnings = 0

function Convert-ToPackagePath {
    param([string]$FullName)

    $fileUri = [System.Uri]::new($FullName)
    return [System.Uri]::UnescapeDataString($script:RootUri.MakeRelativeUri($fileUri).ToString())
}

Write-Host "Dicta package verification"
Write-Host "Root: $root"
Write-Host ""

if (-not (Test-Path -LiteralPath $manifestPath)) {
    Write-Host "[FAIL] manifest.json not found."
    $failures += 1
} else {
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-Host "[OK] manifest.json found: $($manifest.packageName) $($manifest.packageVersion) ($($manifest.packageKind))"
        if ($manifest.packageName -ne "Dicta") {
            Write-Host "[WARN] manifest packageName is unexpected: $($manifest.packageName)"
            $warnings += 1
        }
    } catch {
        Write-Host "[FAIL] manifest.json is not valid JSON: $($_.Exception.Message)"
        $failures += 1
    }
}

if (-not (Test-Path -LiteralPath $shaPath)) {
    Write-Host "[FAIL] SHA256SUMS.txt not found."
    $failures += 1
    exit 1
}

$listed = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$lines = Get-Content -LiteralPath $shaPath -Encoding UTF8
$checked = 0

foreach ($line in $lines) {
    if ([string]::IsNullOrWhiteSpace($line)) {
        continue
    }
    if ($line -notmatch "^([a-fA-F0-9]{64})\s+(.+)$") {
        Write-Host "[FAIL] Bad SHA256SUMS line: $line"
        $failures += 1
        continue
    }

    $expected = $Matches[1].ToLowerInvariant()
    $relative = ($Matches[2]).Trim()
    $relative = $relative.TrimStart("*")
    $relative = $relative -replace "/", "\"
    $full = [System.IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $full.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "[FAIL] Refusing path outside package: $relative"
        $failures += 1
        continue
    }

    $packagePath = Convert-ToPackagePath -FullName $full
    $listed.Add($packagePath) | Out-Null

    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        Write-Host "[FAIL] Missing listed file: $packagePath"
        $failures += 1
        continue
    }

    $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        Write-Host "[FAIL] Hash mismatch: $packagePath"
        $failures += 1
        continue
    }
    $checked += 1
}

Write-Host "[OK] Checked hashes: $checked"

$extraFiles = Get-ChildItem -LiteralPath $root -Recurse -File |
    Where-Object {
        $relative = Convert-ToPackagePath -FullName $_.FullName
        $relative -ne "SHA256SUMS.txt" -and
        $relative -notlike "diagnostics/*" -and
        -not $listed.Contains($relative)
    } |
    Sort-Object @{ Expression = { Convert-ToPackagePath -FullName $_.FullName } }

if ($extraFiles.Count -gt 0) {
    Write-Host "[WARN] Files not listed in SHA256SUMS.txt: $($extraFiles.Count)"
    foreach ($file in $extraFiles | Select-Object -First 20) {
        Write-Host "       $(Convert-ToPackagePath -FullName $file.FullName)"
    }
    if ($extraFiles.Count -gt 20) {
        Write-Host "       ... $($extraFiles.Count - 20) more"
    }
    $warnings += 1
}

Write-Host ""
if ($failures -gt 0) {
    Write-Host "Result: package verification failed."
    exit 1
}

if ($warnings -gt 0) {
    Write-Host "Result: package verification passed with warnings."
    exit 0
}

Write-Host "Result: package verification passed."
