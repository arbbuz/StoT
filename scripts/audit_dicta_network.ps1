param(
    [string]$ProgramPath = "",
    [int]$Seconds = 30
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProgramPath)) {
    $packageRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
    $ProgramPath = Join-Path $packageRoot "Dicta.exe"
}

$resolved = Resolve-Path -LiteralPath $ProgramPath
$program = $resolved.Path
$ruleName = "Dicta Block Outbound"

Write-Host "Dicta network audit"
Write-Host "Program: $program"
Write-Host "Window:  $Seconds seconds"
Write-Host ""

Write-Host "Firewall rule check:"
$netshOutput = @(netsh advfirewall firewall show rule name="$ruleName" verbose 2>$null)
$netshText = ($netshOutput -join "`n")

if ($LASTEXITCODE -eq 0 -and $netshText -like "*$program*") {
    Write-Host "[OK] $ruleName is present for this exact exe."
} elseif ($LASTEXITCODE -eq 0) {
    Write-Host "[WARN] A Dicta firewall rule exists, but not for this exact exe."
    Write-Host $netshText
} else {
    Write-Host "[WARN] Active outbound block rule for this exact exe was not found."
    Write-Host "       Use the app button 'Блокировать сеть' or run:"
    Write-Host "       .\scripts\add_dicta_firewall_block.ps1 -ProgramPath `"$program`""
}

Write-Host ""
Write-Host "Process check:"
$processes = @(Get-Process -Name "Dicta" -ErrorAction SilentlyContinue |
    Where-Object {
        try { $_.Path -eq $program } catch { $false }
    })

if ($processes.Count -eq 0) {
    Write-Host "[WARN] Dicta is not running from this path."
    Write-Host "       Start the app first, then run this audit again."
    exit 0
}

foreach ($proc in $processes) {
    Write-Host "[OK] PID=$($proc.Id) Path=$($proc.Path)"
}

Write-Host ""
Write-Host "Monitoring TCP connections owned by Dicta..."
$deadline = (Get-Date).AddSeconds($Seconds)
$seen = @{}

while ((Get-Date) -lt $deadline) {
    foreach ($proc in $processes) {
        $connections = @(Get-NetTCPConnection -OwningProcess $proc.Id -ErrorAction SilentlyContinue)
        foreach ($conn in $connections) {
            $key = "$($conn.OwningProcess)|$($conn.LocalAddress):$($conn.LocalPort)|$($conn.RemoteAddress):$($conn.RemotePort)|$($conn.State)"
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                Write-Host "[CONNECTION] PID=$($conn.OwningProcess) $($conn.LocalAddress):$($conn.LocalPort) -> $($conn.RemoteAddress):$($conn.RemotePort) $($conn.State)"
            }
        }
    }
    Start-Sleep -Milliseconds 500
}

Write-Host ""
if ($seen.Count -eq 0) {
    Write-Host "[OK] No TCP connections owned by Dicta were observed."
} else {
    Write-Host "[WARN] TCP connection records were observed. Review the lines above."
}
