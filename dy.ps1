#Requires -Version 5.1
<#
.SYNOPSIS
    一条链接 → 抖音评论报告

.DESCRIPTION
    采集 → 生成可视化 HTML → 自动在浏览器打开。
    同时留下一份 JSON，可以直接丢给 AI 分析。

.PARAMETER Link
    作品链接，抖音和 TikTok 都认（网页链接或 App 分享短链均可），
    按域名自动分流。也接受纯作品 ID —— 那种情况下默认按抖音处理，
    要采 TikTok 请加 -TikTok。

.PARAMETER Reply
    连二级回复一起抓。慢很多，但讨论区的内容都在回复里。

.PARAMETER Pages
    最多翻几页，一页 20 条。不给则抓完为止。

.PARAMETER TikTok
    只给作品 ID 时强制按 TikTok 处理。给完整链接则不需要。

.EXAMPLE
    .\dy.ps1 https://www.douyin.com/video/7679845123581070587

.EXAMPLE
    .\dy.ps1 https://www.tiktok.com/@user/video/7123456789012345678 -Reply

.EXAMPLE
    .\dy.ps1 7679845123581070587 -Reply -Pages 5
#>

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Link,

    [switch]$Reply,

    [int]$Pages = 0,

    [switch]$TikTok,

    # 拉二级回复时每条之间的间隔秒数。默认抖音 1.0 / TikTok 2.5。
    # 被限流（提示「响应内容不是有效的 JSON 数据」）时调大。
    [double]$Delay = 0
)

$ErrorActionPreference = 'Stop'

$Here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = 'D:\APP\TikTokDownloader-src\.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) { throw "找不到 Python 环境: $Python" }

$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$fetchArgs = @((Join-Path $Here 'tools\fetch_comments.py'), $Link)
if ($Reply)       { $fetchArgs += '--reply' }
if ($TikTok)      { $fetchArgs += '--tiktok' }
if ($Delay -gt 0) { $fetchArgs += @('--delay', $Delay) }
if ($Pages -gt 0) { $fetchArgs += @('--pages', $Pages) }

Write-Host '采集中…' -ForegroundColor Cyan
$out = & $Python @fetchArgs 2>&1 | Tee-Object -Variable stream | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host '采集失败。' -ForegroundColor Red
    exit 1
}

$jsonPath = ($stream | Select-String -Pattern '^JSON:\s*(.+)$').Matches.Groups[1].Value.Trim()
if (-not $jsonPath -or -not (Test-Path $jsonPath)) {
    Write-Host '没找到采集结果 JSON。' -ForegroundColor Red
    exit 1
}

Write-Host '生成报告…' -ForegroundColor Cyan
$htmlPath = (& $Python (Join-Path $Here 'tools\make_report.py') $jsonPath).Trim()

Write-Host ''
Write-Host "报告  $htmlPath" -ForegroundColor Green
Write-Host "数据  $jsonPath" -ForegroundColor Green
Write-Host '页面右上角「复制给 AI」按钮可以把全部评论拷成纯文本。'

Start-Process $htmlPath
