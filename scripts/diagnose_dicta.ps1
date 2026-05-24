param(
    [string]$Root = "",
    [int]$NetworkSeconds = 10,
    [switch]$SkipNetworkAudit
)

$ErrorActionPreference = "Continue"

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
$diagnosticsDir = Join-Path $root "diagnostics"
New-Item -ItemType Directory -Force -Path $diagnosticsDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$script:ReportPath = Join-Path $diagnosticsDir "dicta_diagnostic_$stamp.txt"
$script:BlockingFailures = 0
$script:Warnings = 0

function Write-ReportLine {
    param([string]$Text = "")

    Write-Host $Text
    Add-Content -LiteralPath $script:ReportPath -Value $Text -Encoding UTF8
}

function Write-Section {
    param([string]$Title)

    Write-ReportLine ""
    Write-ReportLine "=== $Title ==="
}

function Write-Check {
    param(
        [string]$Level,
        [string]$Message,
        [switch]$Blocking
    )

    Write-ReportLine "[$Level] $Message"
    if ($Level -eq "WARN") {
        $script:Warnings += 1
    }
    if ($Level -eq "FAIL" -and $Blocking) {
        $script:BlockingFailures += 1
    }
}

function Invoke-ReportCommand {
    param(
        [string]$Title,
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [int[]]$BlockingExitCodes = @(),
        [switch]$UseStartProcess
    )

    Write-Section $Title
    Write-ReportLine "Command: $FilePath $($Arguments -join ' ')"
    Write-ReportLine ""

    $output = @()
    try {
        if ($UseStartProcess) {
            $safeTitle = ($Title -replace '[^A-Za-z0-9_-]', '_')
            $stdoutPath = Join-Path $env:TEMP "dicta_diag_${safeTitle}_stdout_$PID.txt"
            $stderrPath = Join-Path $env:TEMP "dicta_diag_${safeTitle}_stderr_$PID.txt"
            Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
            $process = Start-Process `
                -FilePath $FilePath `
                -ArgumentList $Arguments `
                -Wait `
                -PassThru `
                -RedirectStandardOutput $stdoutPath `
                -RedirectStandardError $stderrPath `
                -WindowStyle Hidden
            $exitCode = $process.ExitCode
            if (Test-Path -LiteralPath $stdoutPath) {
                $output += Get-Content -LiteralPath $stdoutPath
            }
            if (Test-Path -LiteralPath $stderrPath) {
                $output += Get-Content -LiteralPath $stderrPath
            }
        } else {
            $output = & $FilePath @Arguments 2>&1
            $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
        }
    } catch {
        $output = @($_.Exception.Message)
        $exitCode = 999
    }

    foreach ($line in $output) {
        Write-ReportLine ($line.ToString())
    }

    Write-ReportLine ""
    Write-ReportLine "ExitCode: $exitCode"

    if ($BlockingExitCodes -contains $exitCode) {
        Write-Check -Level "FAIL" -Message "$Title returned blocking exit code $exitCode." -Blocking
    } elseif ($exitCode -ne 0) {
        Write-Check -Level "WARN" -Message "$Title returned exit code $exitCode. Review output above."
    } else {
        Write-Check -Level "OK" -Message "$Title completed."
    }
}

function Test-RequiredFile {
    param(
        [string]$RelativePath,
        [switch]$Hash
    )

    $path = Join-Path $root $RelativePath
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Check -Level "FAIL" -Message "Missing required file: $RelativePath" -Blocking
        return
    }

    $item = Get-Item -LiteralPath $path
    $sizeMb = [math]::Round($item.Length / 1MB, 2)
    Write-Check -Level "OK" -Message "$RelativePath found ($sizeMb MB)."

    if ($Hash) {
        try {
            $sha = Get-FileHash -LiteralPath $path -Algorithm SHA256
            Write-ReportLine "       SHA256: $($sha.Hash)"
        } catch {
            Write-Check -Level "WARN" -Message "Could not calculate SHA256 for ${RelativePath}: $($_.Exception.Message)"
        }
    }
}

function Test-OptionalFile {
    param(
        [string]$RelativePath
    )

    $path = Join-Path $root $RelativePath
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Check -Level "OK" -Message "Optional file not found: $RelativePath. Compat fallback will be used."
        return
    }

    $item = Get-Item -LiteralPath $path
    $sizeMb = [math]::Round($item.Length / 1MB, 2)
    Write-Check -Level "OK" -Message "$RelativePath found ($sizeMb MB)."
}

Write-ReportLine "Dicta unified diagnostic report"
Write-ReportLine "Created:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
Write-ReportLine "Root:     $root"
Write-ReportLine "Report:   $script:ReportPath"

Write-Section "Environment"
Write-ReportLine "Computer: $env:COMPUTERNAME"
Write-ReportLine "User:     $env:USERDOMAIN\$env:USERNAME"
Write-ReportLine "Temp:     $env:TEMP"
Write-ReportLine "PS:       $($PSVersionTable.PSVersion)"
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    Write-ReportLine "Admin:    $isAdmin"
} catch {
    Write-Check -Level "WARN" -Message "Could not determine administrator status: $($_.Exception.Message)"
}
try {
    $os = Get-CimInstance Win32_OperatingSystem
    Write-ReportLine "OS:       $($os.Caption) $($os.Version) build $($os.BuildNumber)"
} catch {
    Write-Check -Level "WARN" -Message "Could not read OS information: $($_.Exception.Message)"
}

Write-Section "Required Files"
Test-RequiredFile -RelativePath "Dicta.exe" -Hash
Test-RequiredFile -RelativePath "manifest.json" -Hash
Test-RequiredFile -RelativePath "SHA256SUMS.txt"
Test-RequiredFile -RelativePath ".tools\whisper.cpp-build-compat\bin\whisper-cli.exe" -Hash
Test-OptionalFile -RelativePath ".tools\whisper.cpp-build-avx2\bin\whisper-cli.exe"
Test-OptionalFile -RelativePath ".tools\whisper.cpp-build-vulkan\bin\whisper-cli.exe"
Test-OptionalFile -RelativePath ".tools\whisper.cpp-build-cuda\bin\whisper-cli.exe"
Test-OptionalFile -RelativePath ".tools\whisper.cpp-build-openvino\bin\whisper-cli.exe"
Test-RequiredFile -RelativePath "models\ggml-tiny-q5_1.bin" -Hash
Test-RequiredFile -RelativePath "models\ggml-base-q5_1.bin" -Hash
Test-RequiredFile -RelativePath "models\ggml-small-q5_1.bin" -Hash
Test-RequiredFile -RelativePath "assets\app_icon.ico"
Test-RequiredFile -RelativePath "docs\IB_PACKAGE_DESCRIPTION.md"
Test-RequiredFile -RelativePath "docs\PROGRAM_LOGIC.md"
Test-RequiredFile -RelativePath "docs\USER_CHECKLIST.md"
Test-RequiredFile -RelativePath "docs\ROADMAP.md"
Test-RequiredFile -RelativePath "docs\STAGE_0_2_1_MICROPHONE.md"
Test-RequiredFile -RelativePath "docs\STAGE_0_2_2_DIAGNOSTICS.md"
Test-RequiredFile -RelativePath "docs\STAGE_0_2_3_ERROR_MESSAGES.md"
Test-RequiredFile -RelativePath "docs\STAGE_0_3_SPEED.md"
Test-RequiredFile -RelativePath "docs\STAGE_0_4_CONVENIENCE.md"
Test-RequiredFile -RelativePath "docs\STAGE_0_5_PERFORMANCE.md"
Test-RequiredFile -RelativePath "scripts\benchmark_dicta_models.cmd"
Test-RequiredFile -RelativePath "scripts\benchmark_dicta_models.ps1"
Test-RequiredFile -RelativePath "scripts\compare_dicta_backends.cmd"
Test-RequiredFile -RelativePath "scripts\compare_dicta_backends.ps1"
Test-RequiredFile -RelativePath "scripts\verify_dicta_package.cmd"
Test-RequiredFile -RelativePath "scripts\verify_dicta_package.ps1"

$program = Join-Path $root "Dicta.exe"
$powershellArgsPrefix = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File")

if (Test-Path -LiteralPath $program) {
    Invoke-ReportCommand `
        -Title "Dicta self-test" `
        -FilePath $program `
        -Arguments @("--self-test") `
        -BlockingExitCodes @(1, 2, 3, 999) `
        -UseStartProcess
} else {
    Write-Section "Dicta self-test"
    Write-Check -Level "FAIL" -Message "Dicta.exe is missing, self-test skipped." -Blocking
}

Invoke-ReportCommand `
    -Title "Package manifest and SHA256 verification" `
    -FilePath "powershell" `
    -Arguments ($powershellArgsPrefix + @((Join-Path $PSScriptRoot "verify_dicta_package.ps1"), "-Root", $root)) `
    -BlockingExitCodes @(1, 999)

Invoke-ReportCommand `
    -Title "Audio devices visible to Dicta" `
    -FilePath "powershell" `
    -Arguments ($powershellArgsPrefix + @((Join-Path $PSScriptRoot "list_audio_devices.ps1"))) `
    -BlockingExitCodes @(999)

if (Test-Path -LiteralPath $program) {
    Invoke-ReportCommand `
        -Title "Microphone quick open test" `
        -FilePath $program `
        -Arguments @("--microphone-diagnostics", "--seconds", "1.0") `
        -BlockingExitCodes @(999) `
        -UseStartProcess
} else {
    Write-Section "Microphone quick open test"
    Write-Check -Level "WARN" -Message "Dicta.exe is missing, microphone open test skipped."
}

Invoke-ReportCommand `
    -Title "Russian Windows spellchecker" `
    -FilePath "powershell" `
    -Arguments ($powershellArgsPrefix + @((Join-Path $PSScriptRoot "check_russian_spellcheck.ps1"))) `
    -BlockingExitCodes @()

Invoke-ReportCommand `
    -Title "Security package check" `
    -FilePath "powershell" `
    -Arguments ($powershellArgsPrefix + @((Join-Path $PSScriptRoot "check_dicta_security.ps1"), "-Root", $root)) `
    -BlockingExitCodes @(1, 999)

Invoke-ReportCommand `
    -Title "Firewall block check" `
    -FilePath "powershell" `
    -Arguments ($powershellArgsPrefix + @((Join-Path $PSScriptRoot "check_firewall_block.ps1"), "-ProgramPath", $program)) `
    -BlockingExitCodes @()

Write-Section "Temporary Dicta Files"
$leftovers = @()
foreach ($pattern in @("dicta_*.wav", "dicta_*_out.txt")) {
    $leftovers += Get-ChildItem -Path $env:TEMP -Filter $pattern -ErrorAction SilentlyContinue
}
if ($leftovers.Count -eq 0) {
    Write-Check -Level "OK" -Message "No Dicta WAV/TXT leftovers found in TEMP."
} else {
    Write-Check -Level "WARN" -Message "Dicta temporary leftovers found in TEMP."
    foreach ($item in $leftovers) {
        Write-ReportLine "       $($item.FullName) ($($item.Length) bytes)"
    }
}

if ($SkipNetworkAudit) {
    Write-Section "Network Audit"
    Write-Check -Level "WARN" -Message "Network audit skipped by parameter."
} else {
    Invoke-ReportCommand `
        -Title "Network audit" `
        -FilePath "powershell" `
        -Arguments ($powershellArgsPrefix + @((Join-Path $PSScriptRoot "audit_dicta_network.ps1"), "-ProgramPath", $program, "-Seconds", "$NetworkSeconds")) `
        -BlockingExitCodes @()
}

Write-Section "Summary"
Write-ReportLine "Blocking failures: $script:BlockingFailures"
Write-ReportLine "Warnings:          $script:Warnings"
Write-ReportLine "Report saved to:   $script:ReportPath"

if ($script:BlockingFailures -gt 0) {
    Write-Check -Level "FAIL" -Message "Diagnostic found blocking issues. Send the report file for analysis." -Blocking
    exit 1
}

if ($script:Warnings -gt 0) {
    Write-Check -Level "WARN" -Message "Diagnostic completed with warnings. Review report before giving it to security."
    exit 0
}

Write-Check -Level "OK" -Message "Diagnostic completed without blocking issues."
exit 0
