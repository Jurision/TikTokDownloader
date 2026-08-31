#Requires -Version 5.1
<#
.SYNOPSIS
    抖音评论采集 —— 独立运行环境启动器

.DESCRIPTION
    这是 D:\APP\TikTokDownloader-src 的一个 git worktree（分支 comments-runtime），
    拥有自己的 Volume\settings.json，与收藏夹自动同步那套配置完全隔离，
    每周的收藏夹同步计划任务不会覆盖这里的设置。

    Python 环境复用主检出的 .venv（依赖完全一致，不重复安装）。

.EXAMPLE
    .\run-comments.ps1
#>

$ErrorActionPreference = 'Stop'

$Here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = 'D:\APP\TikTokDownloader-src\.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw "找不到 Python 环境: $Python`n请先在 D:\APP\TikTokDownloader-src 执行 uv sync"
}

# 采集加密参数依赖 Node.js（>=18）
$Node = Get-Command node -ErrorAction SilentlyContinue
if (-not $Node) {
    Write-Warning ' 未检测到 Node.js，抖音接口的加密参数将无法生成，采集会失败。'
}

# UTF-8 输出，避免终端里中文评论变乱码
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Push-Location $Here
try {
    & $Python main.py
}
finally {
    Pop-Location
}
