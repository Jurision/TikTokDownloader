[CmdletBinding()]
param(
    [string]$SourceRoot = '',
    [string]$Config = '',
    [string]$PythonPath = '',
    [string]$OutputRoot = '',
    [string]$FolderName = '',
    [string]$OwnerUrl = '',
    [string]$Browser = '',
    [switch]$SkipCookieRefresh,
    [switch]$ConfigOnly,
    [switch]$AllowMissingOwner,
    [switch]$AllowMissingCookie,
    [switch]$NoInstall
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
if ($OutputRoot) {
    $SyncConfig['output_root'] = Expand-DouyinFavoritesConfigValue $OutputRoot
}
if ($FolderName) {
    $SyncConfig['folder_name'] = $FolderName
}
if ($OwnerUrl) {
    $SyncConfig['owner_url'] = $OwnerUrl
}
if ($Browser) {
    $SyncConfig['browser'] = $Browser
}
if ($SkipCookieRefresh) {
    $SyncConfig['skip_cookie_refresh'] = $true
}
if ($AllowMissingOwner) {
    $SyncConfig['allow_missing_owner'] = $true
}
if ($AllowMissingCookie) {
    $SyncConfig['allow_missing_cookie'] = $true
}

function Write-Step {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    Add-Content -LiteralPath $script:LogFile -Value $line -Encoding UTF8
}

function Invoke-Logged {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    Write-Step ("RUN {0} {1}" -f $FilePath, ($Arguments -join ' '))
    Push-Location -LiteralPath $WorkingDirectory
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        foreach ($line in $output) {
            $text = [string]$line
            Write-Host $text
            Add-Content -LiteralPath $script:LogFile -Value $text -Encoding UTF8
        }
        return $exitCode
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
        Pop-Location
    }
}

$OutputRoot = ([string]$SyncConfig['output_root']).TrimEnd('\')
$LogDir = Join-Path $OutputRoot 'Logs'
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$script:LogFile = Join-Path $LogDir "douyin-favorites-sync-$stamp.log"
New-Item -ItemType File -Path $script:LogFile -Force | Out-Null

Write-Step "Starting Douyin favorites sync"
Write-Step "SourceRoot: $SourceRoot"
Write-Step "OutputRoot: $OutputRoot"
if ($SyncConfig['config_path']) {
    Write-Step "Config: $($SyncConfig['config_path'])"
}

$MainPy = Join-Path $SourceRoot 'main.py'
$PreparePy = Join-Path $SourceRoot 'automation\prepare_douyin_sync.py'
$Requirements = Join-Path $SourceRoot 'requirements.txt'
if (-not (Test-Path -LiteralPath $MainPy)) {
    throw "main.py not found: $MainPy"
}
if (-not (Test-Path -LiteralPath $PreparePy)) {
    throw "prepare helper not found: $PreparePy"
}

$VenvRoot = Join-Path $SourceRoot '.venv'
$VenvPython = Join-Path $VenvRoot 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
    if ($NoInstall) {
        throw "Virtual environment is missing and -NoInstall was specified: $VenvPython"
    }
    $PythonCommand = Resolve-DouyinFavoritesPythonCommand -PythonPath $PythonPath
    Write-Step "Creating virtual environment"
    $code = Invoke-Logged `
        -FilePath $PythonCommand.FilePath `
        -Arguments ($PythonCommand.Arguments + @('-m', 'venv', $VenvRoot)) `
        -WorkingDirectory $SourceRoot
    if ($code -ne 0) {
        throw "venv creation failed with exit code $code"
    }
}

if (-not $NoInstall) {
    Write-Step "Installing/updating Python dependencies"
    $code = Invoke-Logged -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', '-r', $Requirements, 'rookiepy') -WorkingDirectory $SourceRoot
    if ($code -ne 0) {
        throw "dependency installation failed with exit code $code"
    }
}

$PrepareArgs = @(
    $PreparePy,
    '--volume', (Join-Path $SourceRoot 'Volume'),
    '--output-root', $OutputRoot,
    '--folder-name', ([string]$SyncConfig['folder_name']),
    '--run-command', ([string]$SyncConfig['run_command']),
    '--browser', ([string]$SyncConfig['browser'])
)
if ($SyncConfig['config_path']) {
    $PrepareArgs += @('--config', ([string]$SyncConfig['config_path']))
}
if ($SyncConfig['owner_url']) {
    $PrepareArgs += @('--owner-url', ([string]$SyncConfig['owner_url']))
}
if ([bool]$SyncConfig['skip_cookie_refresh']) {
    $PrepareArgs += '--skip-cookie-refresh'
}
if ([bool]$SyncConfig['allow_missing_owner']) {
    $PrepareArgs += '--allow-missing-owner'
}
if ([bool]$SyncConfig['allow_missing_cookie']) {
    $PrepareArgs += '--allow-missing-cookie'
}

Write-Step "Preparing settings and database"
$prepareExit = Invoke-Logged -FilePath $VenvPython -Arguments $PrepareArgs -WorkingDirectory $SourceRoot
if ($prepareExit -ne 0) {
    Write-Step "Prepare step failed with exit code $prepareExit"
    Write-Step "See log: $script:LogFile"
    exit $prepareExit
}

if ($ConfigOnly) {
    Write-Step "ConfigOnly requested; stopping before downloader run"
    Write-Step "Log written to $script:LogFile"
    exit 0
}

Write-Step "Running DouK-Downloader source entry point"
$runExit = Invoke-Logged -FilePath $VenvPython -Arguments @($MainPy) -WorkingDirectory $SourceRoot
Write-Step "Downloader exited with code $runExit"
Write-Step "Log written to $script:LogFile"
exit $runExit
