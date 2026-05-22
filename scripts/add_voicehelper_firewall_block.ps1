param(
    [string]$ProgramPath = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProgramPath)) {
    $ProgramPath = (Get-Command python).Source
}

$resolved = Resolve-Path -LiteralPath $ProgramPath
$ruleName = "VoiceHelper Block Outbound"

Write-Host "Будет создано правило Windows Firewall для запрета исходящих соединений:"
Write-Host "  $ruleName"
Write-Host "  $($resolved.Path)"
Write-Host ""
Write-Host "Важно: если указан python.exe, правило заблокирует сеть для этого Python, а не только для VoiceHelper."
Write-Host "Для будущей .exe-сборки лучше передать путь именно к VoiceHelper.exe."

$existing = @(Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
    Where-Object { $_.Direction -eq "Outbound" -and $_.Action -eq "Block" } |
    Where-Object { ($_ | Get-NetFirewallApplicationFilter).Program -eq $resolved.Path })

if ($existing.Count -eq 0) {
    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Outbound `
        -Program $resolved.Path `
        -Action Block `
        -Profile Any `
        -Description "VoiceHelper confidentiality control: block outbound network access."
} else {
    Write-Host "Подходящее правило уже существует."
}

Write-Host "Готово."
