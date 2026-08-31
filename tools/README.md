# 评论采集使用说明

这个目录是在 `Jurision/TikTokDownloader` fork 上加的一套评论采集工具，
跑在分支 `comments-runtime` 上，位置 `D:\APP\TikTokDownloader-comments`。

它是 `D:\APP\TikTokDownloader-src` 的一个 **git worktree**，有自己的 `Volume\`，
所以每周的收藏夹同步任务重写配置时碰不到这里。Python 复用 `-src` 的 `.venv`。

---

## 日常就一条命令

```powershell
D:\APP\TikTokDownloader-comments\dy.ps1 <链接>
```

采集 → 生成 HTML 报告 → 自动在浏览器打开。抖音和 TikTok 都认，**按域名自动分流**。

产物两份，同名成对放在 `Volume\reports\`：

| 文件 | 用途 |
|---|---|
| `comments-<时间戳>.html` | 可视化报告，浏览器直接看 |
| `comments-<时间戳>.json` | 完整原始字段，丢给 AI 分析 |

报告页右上角 **「复制给 AI」** 按钮，把全部评论拷成纯文本，粘给任何 AI 就能分析。

程序自带的 CSV 照常写到 `D:\APP\DouyinComments\Data\`。

### 常用参数

```powershell
# 连二级回复一起抓
dy.ps1 <链接> -Reply

# 只抓前 5 页（一页 20 条），试水或大视频限量用
dy.ps1 <链接> -Pages 5

# 被限流时放慢拉回复的节奏（秒）
dy.ps1 <链接> -Reply -Delay 5

# 只有作品 ID 没有链接时，默认按抖音；采 TikTok 要加 -TikTok
dy.ps1 7679845123581070587 -TikTok
```

**TikTok 一律从 `-Pages 2` 起步**，确认没被限再放开。

---

## Cookie 过期了怎么办

症状：采不到数据，或提示 Cookie 未设置。

1. 浏览器打开已登录的 douyin.com / tiktok.com
2. `F12` → Network → 过滤框输 `douyin.com/aweme`（TikTok 输 `tiktok.com/api`）
3. `F5` 刷新，**左边名称列表里右键任意一条请求 → 复制 → 复制为 cURL**
4. 跑：

```powershell
D:\APP\TikTokDownloader-comments\set-cookie.ps1           # 抖音
D:\APP\TikTokDownloader-comments\set-cookie.ps1 -TikTok   # TikTok
```

三种 cURL 变体（bash / cmd / PowerShell）、纯 Cookie 串、多行 header 块都能认。
复制错了会明确告诉你错在哪，不会把垃圾写进配置。

**Cookie 等同于登录凭证，不要贴进聊天或截完整的图。** 脚本全程不打印它的内容。

### 备用：直接读浏览器

```powershell
set-cookie.ps1 -TikTok -FromBrowser firefox
```

绕开 DevTools 复制。注意 Chrome/Edge v130+ 因 app-bound 加密需要管理员权限，
Firefox 没有这个限制——但前提是你在 Firefox 里登录过。

---

## 上游有更新时

抖音／TikTok 的接口签名经常变，采集突然全面失败时先跑这个：

```powershell
D:\APP\TikTokDownloader-comments\update-from-upstream.ps1
```

它会 fetch 上游 → 合并进 master → 推到你的 fork → `uv sync` →
补回 `rookiepy`（上游已移除但收藏夹同步要用）→ 把本 worktree 快进到 master。

`Volume\` 被 gitignore，升级不动你的配置和 Cookie。

---

## 排错

**「响应内容不是有效的 JSON 数据，请尝试更新 Cookie！」**

**这句提示是误导的，通常跟 Cookie 无关，是限流。** TikTok 尤其敏感。
换 Cookie 没用，只能等，冷却以十分钟计。**不要重试**——每次失败请求都会延长冷却。
下次用 `-Delay` 调大间隔、`-Pages` 压小范围。

**「加密参数代码文件不存在！」**

无害，可以忽略。`encipher.py` 是可选的加密参数覆盖文件，
缺了会自动回退到内置的 `src/encrypt/douyin_params.py`。

**采集要 Node.js**

签名参数靠 Node 执行 JS 生成，需要 **Node.js ≥ 18**。

---

## 平台差异

| 字段 | 抖音 | TikTok |
|---|---|---|
| 评论内容 / 点赞 / 时间 | ✅ | ✅ |
| 二级回复 | ✅ 已验证 | ⚠️ 未验证（每次都撞限流） |
| IP 归属地 | ✅ 省份 | ❌ 恒为「未知」 |
| `unique_id`（账号 @） | ❌ 空 | ✅ |
| 签名 / 年龄 | 部分 | ❌ 全空 |

TikTok 报告里的地区分布图是空的——平台不返回这个字段，不是采集出了问题。
