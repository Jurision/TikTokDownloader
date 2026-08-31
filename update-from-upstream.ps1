#Requires -Version 5.1
<#
.SYNOPSIS
    同步上游 JoeanAmier/TikTokDownloader 的更新

.DESCRIPTION
    抖音接口的请求头/加密参数经常变动，采集失败时先跑这个脚本。
    流程：
      1. 主检出 fetch upstream，把 upstream/master 合并进 master 并推到你的 fork
      2. 依赖变化时 uv sync（并补回自动化用到的 rookiepy）
      3. 本 worktree 快进到 master

    Volume\settings.json 已被 .gitignore 忽略，升级不会动你的配置。
#>

$ErrorActionPreference = 'Stop'

$Src  = 'D:\APP\TikTokDownloader-src'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host '[1/4] 拉取上游…' -ForegroundColor Cyan
git -C $Src fetch upstream

$Behind = git -C $Src rev-list --count master..upstream/master
if ($Behind -eq '0') {
    Write-Host '已是最新，无需更新。' -ForegroundColor Green
}
else {
    Write-Host "上游领先 $Behind 个提交，开始合并…" -ForegroundColor Cyan
    git -C $Src tag -f "backup-before-sync-$(Get-Date -Format yyyyMMdd-HHmmss)" master
    git -C $Src checkout master
    git -C $Src merge upstream/master
    git -C $Src push origin master
}

Write-Host '[2/4] 同步依赖…' -ForegroundColor Cyan
Push-Location $Src
try {
    uv sync
    # 上游已移除 rookiepy，但 automation/prepare_douyin_sync.py 靠它读浏览器 Cookie，
    # 每次 uv sync 都会把它删掉，这里补回来。
    uv pip install rookiepy
}
finally {
    Pop-Location
}

Write-Host '[3/4] 更新评论采集 worktree…' -ForegroundColor Cyan
git -C $Here merge master

Write-Host '[4/4] 完成。' -ForegroundColor Green
git -C $Here log --oneline -1
