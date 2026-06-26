[CmdletBinding()]
param(
    [string]$SourceRoot = '',
    [string]$OutputRoot = '',
    [string]$FolderName = '',
    [string]$OwnerUrl = '',
    [string]$Browser = '',
    [ValidateSet('', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')]
    [string]$DayOfWeek = '',
    [string]$At = '',
    [string]$TaskName = '',
    [switch]$NoRegister
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

$configPath = Get-DouyinFavoritesDefaultConfigPath -SourceRoot $SourceRoot
$config = Read-DouyinFavoritesSyncConfig -SourceRoot $SourceRoot

function Read-WithDefault {
    param(
        [string]$Prompt,
        [string]$Default
    )

    $value = Read-Host "$Prompt [$Default]"
    if ($value) {
        return $value
    }
    return $Default
}

if (-not $OutputRoot) {
    $OutputRoot = Read-WithDefault -Prompt 'Download folder' -Default ([string]$config['output_root'])
}
if (-not $FolderName) {
    $FolderName = Read-WithDefault -Prompt 'Downloader folder name' -Default ([string]$config['folder_name'])
}
if (-not $OwnerUrl) {
    $OwnerUrl = Read-WithDefault -Prompt 'Douyin homepage URL' -Default ([string]$config['owner_url'])
}
if (-not $Browser) {
    $Browser = Read-WithDefault -Prompt 'Browser for cookie refresh' -Default ([string]$config['browser'])
}
if (-not $DayOfWeek) {
    $DayOfWeek = Read-WithDefault -Prompt 'Weekly sync day' -Default ([string]$config['day_of_week'])
}
if (-not $At) {
    $At = Read-WithDefault -Prompt 'Weekly sync time HH:mm' -Default ([string]$config['at'])
}
if (-not $TaskName) {
    $TaskName = Read-WithDefault -Prompt 'Scheduled task name' -Default ([string]$config['task_name'])
}

$localConfig = [ordered]@{
    output_root = $OutputRoot
    folder_name = $FolderName
    owner_url = $OwnerUrl
    browser = $Browser
    run_command = [string]$config['run_command']
    task_name = $TaskName
    day_of_week = $DayOfWeek
    at = $At
    skip_cookie_refresh = [bool]$config['skip_cookie_refresh']
    allow_missing_owner = [bool]$config['allow_missing_owner']
    allow_missing_cookie = [bool]$config['allow_missing_cookie']
}

$localConfig | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $configPath -Encoding UTF8
Write-Host "Wrote local config: $configPath"

if (-not $NoRegister) {
    $installer = Join-Path $SourceRoot 'automation\install_weekly_task.ps1'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -SourceRoot $SourceRoot -Config $configPath
}
