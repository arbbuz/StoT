param(
    [string]$Root = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Root)) {
    $root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
} else {
    $root = Resolve-Path -LiteralPath $Root
}
$whisper = Join-Path $root ".tools\whisper.cpp-build-compat\bin\whisper-cli.exe"
$manifest = Join-Path $root "manifest.json"
$shaSums = Join-Path $root "SHA256SUMS.txt"
$verifyScript = Join-Path $root "scripts\verify_dicta_package.ps1"
$supportedModels = @(
    "ggml-small-q5_1.bin",
    "ggml-small.bin",
    "ggml-medium-q5_0.bin",
    "ggml-medium.bin",
    "ggml-large-v3-turbo-q5_0.bin",
    "ggml-large-v3-turbo.bin"
)
$tempPatterns = @(
    "dicta_*.wav",
    "dicta_*_out.txt"
)

Write-Host "Dicta security check"
Write-Host "Root: $root"
Write-Host ""

$ok = $true

if (Test-Path -LiteralPath $whisper) {
    Write-Host "[OK] whisper-cli found: $whisper"
} else {
    Write-Host "[FAIL] whisper-cli not found: $whisper"
    $ok = $false
}

if (Test-Path -LiteralPath $manifest) {
    Write-Host "[OK] manifest found: $manifest"
} else {
    Write-Host "[FAIL] manifest not found: $manifest"
    $ok = $false
}

if (Test-Path -LiteralPath $shaSums) {
    Write-Host "[OK] SHA256SUMS found: $shaSums"
} else {
    Write-Host "[FAIL] SHA256SUMS not found: $shaSums"
    $ok = $false
}

if (Test-Path -LiteralPath $verifyScript) {
    Write-Host ""
    Write-Host "Package manifest verification:"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $verifyScript -Root $root
    if ($LASTEXITCODE -ne 0) {
        $ok = $false
    }
} else {
    Write-Host "[WARN] package verification script not found: $verifyScript"
}

$foundModels = @()
foreach ($modelName in $supportedModels) {
    $model = Join-Path $root "models\$modelName"
    if (Test-Path -LiteralPath $model) {
        $item = Get-Item -LiteralPath $model
        $foundModels += $item
        Write-Host "[OK] model found: $($item.Name) ($([math]::Round($item.Length / 1MB, 1)) MB)"
    }
}
if ($foundModels.Count -eq 0) {
    Write-Host "[FAIL] no supported Dicta model found in: $(Join-Path $root 'models')"
    Write-Host "       Copy at least one supported ggml-*.bin model into the models folder."
    $ok = $false
}

Write-Host ""
Write-Host "Firewall rules matching Dicta:"
$netshOutput = @(netsh advfirewall firewall show rule name="Dicta Block Outbound" verbose 2>$null)
$netshText = ($netshOutput -join "`n")
$programText = $whisper -replace "\\.tools\\whisper\.cpp-build-compat\\bin\\whisper-cli\.exe$", "Dicta.exe"

if ($LASTEXITCODE -eq 0 -and $netshText -like "*$programText*") {
    Write-Host "[OK] Dicta Block Outbound is present for: $programText"
} elseif ($LASTEXITCODE -eq 0) {
    Write-Host "[WARN] Dicta firewall rule exists, but not for this checked root."
    Write-Host $netshText
} else {
    Write-Host "[WARN] Dicta outbound firewall rule was not found."
    Write-Host "       Create it manually when ready: .\scripts\add_dicta_firewall_block.ps1"
}

Write-Host ""
Write-Host "Temporary Dicta files:"
$leftovers = @()
foreach ($pattern in $tempPatterns) {
    $leftovers += Get-ChildItem -Path $env:TEMP -Filter $pattern -ErrorAction SilentlyContinue
}

if ($leftovers.Count -eq 0) {
    Write-Host "[OK] no Dicta temp WAV/TXT leftovers found in $env:TEMP"
} else {
    Write-Host "[WARN] temp leftovers found:"
    foreach ($item in $leftovers) {
        Write-Host "       $($item.FullName)"
    }
}

Write-Host ""
if ($ok) {
    Write-Host "Result: basic local files check passed."
} else {
    Write-Host "Result: security check found blocking issues."
    exit 1
}
