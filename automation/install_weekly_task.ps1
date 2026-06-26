[CmdletBinding()]
param(
    [string]$SourceRoot = '',
    [string]$Config = '',
    [string]$TaskName = '',
    [ValidateSet('', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')]
    [string]$DayOfWeek = '',
    [string]$At = '',
    [string]$OwnerUrl = '',
    [string]$OutputRoot = '',
    [string]$Browser = '',
    [switch]$DisableLimitedFallback
)

$ErrorActionPreference = 'Stop'

$ScriptDir = if ($PSScriptRoot) {
    $PSScriptRoot
}
else {
    Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not $SourceRoot) {
    $SourceRoot = (Resolve-Path -LiteralPath (Join-Path $ScriptDir '..')).Path
}
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path

. (Join-Path $SourceRoot 'automation\douyin_favorites_config.ps1')

$SyncConfig = Read-DouyinFavoritesSyncConfig -SourceRoot $SourceRoot -ConfigPath $Config
if ($TaskName) {
    $SyncConfig['task_name'] = $TaskName
}
if ($DayOfWeek) {
    $SyncConfig['day_of_week'] = $DayOfWeek
}
if ($At) {
    $SyncConfig['at'] = $At
}
if ($OwnerUrl) {
    $SyncConfig['owner_url'] = $OwnerUrl
}
if ($OutputRoot) {
    $SyncConfig['output_root'] = Expand-DouyinFavoritesConfigValue $OutputRoot
}
if ($Browser) {
    $SyncConfig['browser'] = $Browser
}

$SyncScript = Join-Path $SourceRoot 'automation\sync_douyin_favorites.ps1'
if (-not (Test-Path -LiteralPath $SyncScript)) {
    throw "sync script not found: $SyncScript"
}

$time = [datetime]::ParseExact([string]$SyncConfig['at'], 'HH:mm', [System.Globalization.CultureInfo]::InvariantCulture)
$argumentParts = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', ('"{0}"' -f $SyncScript),
    '-SourceRoot', ('"{0}"' -f $SourceRoot)
)
if ($SyncConfig['config_path']) {
    $argumentParts += @('-Config', ('"{0}"' -f $SyncConfig['config_path']))
}
if (-not $SyncConfig['config_path'] -or $OutputRoot) {
    $argumentParts += @('-OutputRoot', ('"{0}"' -f $SyncConfig['output_root']))
}
if (-not $SyncConfig['config_path'] -or $Browser) {
    $argumentParts += @('-Browser', ('"{0}"' -f $SyncConfig['browser']))
}
if ($OwnerUrl) {
    $argumentParts += @('-OwnerUrl', ('"{0}"' -f $SyncConfig['owner_url']))
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ($argumentParts -join ' ') `
    -WorkingDirectory $SourceRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek ([string]$SyncConfig['day_of_week']) -At $time
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $CurrentUser `
    -LogonType Interactive `
    -RunLevel Highest

$description = 'Weekly sync for Douyin favorited works via Jurision/TikTokDownloader source.'
$registeredHighest = $true
try {
    Register-ScheduledTask `
        -TaskName ([string]$SyncConfig['task_name']) `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $description `
        -Force | Out-Null
}
catch {
    if ($DisableLimitedFallback) {
        throw
    }
    $registeredHighest = $false
    Write-Warning "Registering with RunLevel Highest failed: $($_.Exception.Message)"
    Write-Warning "Falling back to a standard scheduled task. Run this script from an elevated PowerShell window later to upgrade it."
    Register-ScheduledTask `
        -TaskName ([string]$SyncConfig['task_name']) `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description $description `
        -Force | Out-Null
}

$task = Get-ScheduledTask -TaskName ([string]$SyncConfig['task_name'])
$task | Select-Object TaskName, State, @{Name = 'RunLevelHighest'; Expression = { $registeredHighest } }
