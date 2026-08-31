#Requires -Version 5.1
<#
.SYNOPSIS
    把剪贴板里的抖音 Cookie 写进本 worktree 的 Volume\settings.json

.DESCRIPTION
    比程序内置的「从剪贴板读取 Cookie」宽容：
    纯 Cookie 串、带 "Cookie:" 前缀、DevTools 的「复制为 cURL」、
    整块 header 文本 —— 都能认出来。

    写入前会校验登录态字段（sessionid / sessionid_ss / sid_tt），
    复制错东西（比如请求 URL）会直接报错而不是写进去。

    Cookie 通过管道传给 Python，不出现在命令行里，也不会被回显。

.PARAMETER TikTok
    写入 cookie_tiktok（TikTok 平台），不加则写抖音的 cookie。

.EXAMPLE
    # 在 DevTools 里复制好 Cookie 值之后
    .\set-cookie.ps1

.EXAMPLE
    .\set-cookie.ps1 -TikTok
#>

param(
    [switch]$TikTok,

    # 直接从浏览器 Cookie 库读取，绕开 DevTools 复制。
    # Chrome/Edge v130+ 需管理员权限；Firefox 无此限制。
    [string]$FromBrowser
)

$ErrorActionPreference = 'Stop'

$Here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = 'D:\APP\TikTokDownloader-src\.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw "找不到 Python 环境: $Python"
}

$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$pyArgs = @((Join-Path $Here 'tools\set_cookie.py'))
if ($TikTok) { $pyArgs += '--tiktok' }

if ($FromBrowser) {
    $pyArgs += @('--browser', $FromBrowser)
    & $Python @pyArgs
}
else {
    $raw = Get-Clipboard -Raw
    if ([string]::IsNullOrWhiteSpace($raw)) {
        Write-Host '剪贴板是空的。' -ForegroundColor Red
        exit 2
    }
    $raw | & $Python @pyArgs
}
$code = $LASTEXITCODE

if ($code -eq 0) {
    Write-Host ''
    Write-Host '搞定。接着跑 .\run-comments.ps1，直接选 5 进终端交互模式即可（不用再选 2）。' -ForegroundColor Green
}
exit $code
