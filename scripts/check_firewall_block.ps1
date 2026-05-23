param(
    [string]$ProgramPath = "",
    [string]$RuleName = "Dicta Block Outbound"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProgramPath)) {
    $packageRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
    $ProgramPath = Join-Path $packageRoot "Dicta.exe"
}

$resolved = Resolve-Path -LiteralPath $ProgramPath
$program = $resolved.Path

Write-Host "Dicta firewall block check"
Write-Host "Rule:    $RuleName"
Write-Host "Program: $program"
Write-Host ""

$netshOutput = @(netsh advfirewall firewall show rule name="$RuleName" verbose 2>$null)
$netshExit = $LASTEXITCODE
$netshText = ($netshOutput -join "`n")
$normalizedOutput = $netshText.ToLowerInvariant()
$normalizedProgram = $program.ToLowerInvariant()

if ($netshExit -ne 0 -or [string]::IsNullOrWhiteSpace($netshText)) {
    Write-Host "[FAIL] Firewall rule was not found."
    Write-Host "       In Dicta click: Блокировать сеть"
    exit 1
}

if ($normalizedOutput -notlike "*$normalizedProgram*") {
    Write-Host "[FAIL] Rule exists, but it is not bound to this exact Dicta.exe."
    Write-Host ""
    Write-Host "Raw netsh output:"
    Write-Host $netshText
    exit 2
}

$looksBlocked = (
    $normalizedOutput -like "*action*block*" -or
    $normalizedOutput -like "*действие*блок*" -or
    $normalizedOutput -like "*блокировать*"
)

if (-not $looksBlocked) {
    Write-Host "[WARN] Rule is bound to this exe, but block action was not recognized in localized netsh output."
    Write-Host "       Please review raw output below."
    Write-Host ""
    Write-Host $netshText
    exit 3
}

Write-Host "[OK] Outbound firewall block is enabled for this exact Dicta.exe."
exit 0
