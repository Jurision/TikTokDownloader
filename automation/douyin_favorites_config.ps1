[CmdletBinding()]
param()

function Get-DouyinFavoritesDefaultOutputRoot {
    Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Downloads\DouyinFavorites'
}

function Expand-DouyinFavoritesConfigValue {
    param([string]$Value)

    if (-not $Value) {
        return ''
    }
    $expanded = [Environment]::ExpandEnvironmentVariables($Value.Trim())
    if ($expanded -eq '~') {
        return $HOME
    }
    if ($expanded.StartsWith('~\') -or $expanded.StartsWith('~/')) {
        return Join-Path $HOME $expanded.Substring(2)
    }
    return $expanded
}

function Get-DouyinFavoritesDefaultConfigPath {
    param([Parameter(Mandatory = $true)][string]$SourceRoot)

    Join-Path $SourceRoot 'automation\douyin_favorites_sync.local.json'
}

function Read-DouyinFavoritesSyncConfig {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [string]$ConfigPath = ''
    )

    $resolvedConfigPath = ''
    if ($ConfigPath) {
        if (-not (Test-Path -LiteralPath $ConfigPath)) {
            throw "Config file not found: $ConfigPath"
        }
        $resolvedConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
    }
    else {
        $defaultConfigPath = Get-DouyinFavoritesDefaultConfigPath -SourceRoot $SourceRoot
        if (Test-Path -LiteralPath $defaultConfigPath) {
            $resolvedConfigPath = (Resolve-Path -LiteralPath $defaultConfigPath).Path
        }
    }

    $config = [ordered]@{
        output_root = Get-DouyinFavoritesDefaultOutputRoot
        folder_name = 'DouyinFavorites'
        owner_url = ''
        browser = 'Chrome'
        run_command = '3 9 Q'
        task_name = 'DouyinFavoritesWeeklySync'
        day_of_week = 'Sunday'
        at = '03:30'
        skip_cookie_refresh = $false
        allow_missing_owner = $false
        allow_missing_cookie = $false
        config_path = $resolvedConfigPath
    }

    if ($resolvedConfigPath) {
        $raw = Get-Content -LiteralPath $resolvedConfigPath -Raw -Encoding UTF8
        $loaded = $raw | ConvertFrom-Json
        foreach ($property in $loaded.PSObject.Properties) {
            if ($null -ne $property.Value -and $config.Contains($property.Name)) {
                $config[$property.Name] = $property.Value
            }
        }
    }

    $config['output_root'] = Expand-DouyinFavoritesConfigValue ([string]$config['output_root'])
    return $config
}

function Test-DouyinFavoritesPython {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )

    try {
        & $FilePath @Arguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" | Out-Null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Resolve-DouyinFavoritesPythonCommand {
    param([string]$PythonPath = '')

    if ($PythonPath) {
        $expanded = Expand-DouyinFavoritesConfigValue $PythonPath
        if (-not (Test-Path -LiteralPath $expanded)) {
            throw "Python runtime not found: $expanded"
        }
        if (-not (Test-DouyinFavoritesPython -FilePath $expanded)) {
            throw "Python runtime must be 3.12 or newer: $expanded"
        }
        return [pscustomobject]@{ FilePath = $expanded; Arguments = @() }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        if (Test-DouyinFavoritesPython -FilePath 'py' -Arguments @('-3.12')) {
            return [pscustomobject]@{ FilePath = 'py'; Arguments = @('-3.12') }
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        if (Test-DouyinFavoritesPython -FilePath 'python') {
            return [pscustomobject]@{ FilePath = 'python'; Arguments = @() }
        }
    }

    throw 'Python 3.12 was not found. Install Python 3.12, or rerun with -PythonPath "C:\Path\To\python.exe".'
}
