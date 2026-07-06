# 私有下载面板部署

这个目录用于把个人 DouK-Downloader 面板作为内部 Docker 服务运行，并接入现有的 navi 门禁和 Caddy 反向代理。

Do not publish a host port for this service. 浏览器访问应只通过 Caddy 的 `/downloads` 路径进入；Caddy 先用 `forward_auth` 通过 `navi-save:8099` 校验已有的 `navi_session`，再把请求转发到内部 Docker 网络里的 `douk-private-panel:5555`。

## 文件

- `docker-compose.yml`：构建并运行内部面板服务，不声明 `ports`。
- `env.example`：复制为 `.env` 后填写 `DOUK_PRIVATE_TOKEN`，用于脚本或 API 直接调用。

`DOUK_PRIVATE_TOKEN` 只适合内部直连服务，或以后另建一条明确的私有 API 路由。这个文档里的公网 `/downloads` 路由仍然只走 navi 门禁。

## 启动前准备

这些命令需要在完整仓库 checkout 的根目录运行，因为 `docker-compose.yml` 使用 `../..` 作为构建上下文。不要只复制 `deploy/private-panel` 目录到服务器单独运行。

1. 确认 Caddy/navi 所在 Docker 网络名为 `oceverse_halo_network`。
2. 复制环境文件。VPS / Linux:

   ```bash
   cp deploy/private-panel/env.example deploy/private-panel/.env
   chmod 600 deploy/private-panel/.env
   ```

   Windows 本地检查可用：

   ```powershell
   Copy-Item deploy/private-panel/env.example deploy/private-panel/.env
   ```

3. 在 `.env` 中填写一个足够长的随机 `DOUK_PRIVATE_TOKEN`。
4. 填写 `DOUK_TRUSTED_PROXY_SECRET`，并在 Caddy 进程里设置同名环境变量。面板只接受带有匹配 `X-Douk-Trusted-Proxy` 内部头的 navi 身份请求。
5. 如果 navi 里可能存在多个可登录用户，填写 `DOUK_ALLOWED_NAVI_USER_IDS` 或 `DOUK_ALLOWED_NAVI_USER_EMAILS`，用英文逗号分隔。留空表示信任这条 navi 路由已经是 owner-only。
6. 确认持久卷中的 `/app/Volume/settings.json` 已配置下载所需 Cookie。没有 Cookie 时，提交任务会入队，但下载会失败。

## 预检

部署前先验证 Compose 配置：

```powershell
docker compose -f deploy/private-panel/docker-compose.yml config --quiet
```

如果这一步提示缺少 `.env`，先按上面的步骤从 `env.example` 创建 `.env`。如果提示找不到 `oceverse_halo_network`，先确认 Caddy/navi 所在 Docker 网络已经创建并且 Caddy 容器也加入了该网络。

## 启动服务

在仓库根目录运行：

```powershell
docker compose -f deploy/private-panel/docker-compose.yml up -d --build
```

确认服务没有公开宿主机端口：

```powershell
docker compose -f deploy/private-panel/docker-compose.yml ps
```

## Caddy 路由形状

把 `/downloads` 和 `/downloads/*` 加入 navi-gated matcher。必须使用 `route` 保持执行顺序：先移除外部请求伪造的身份头，再走 `forward_auth`，最后代理到内部服务：

```caddy
@downloads_gated {
    path /downloads /downloads/*
}

route @downloads_gated {
    request_header -X-Tradedocs-User-Id
    request_header -X-Tradedocs-User-Email
    request_header -X-Tradedocs-User-Name
    request_header -X-Douk-Trusted-Proxy

    forward_auth @downloads_gated navi-save:8099 {
        uri /navi/verify
        copy_headers X-Tradedocs-User-Id X-Tradedocs-User-Email X-Tradedocs-User-Name
    }

    redir /downloads /downloads/ 308

    reverse_proxy /downloads/* douk-private-panel:5555 {
        header_up X-Douk-Trusted-Proxy "{env.DOUK_TRUSTED_PROXY_SECRET}"
    }
}
```

## 首次验证

1. 未登录 navi 时打开 `/downloads/`，应跳转到 `/navi/login`。
2. 登录 navi 后打开 `/downloads/`，应能看到私有下载面板。
3. 检查 `/downloads/api/health`。如果 worker 已退出、`DOUK_TRUSTED_PROXY_SECRET`/`DOUK_PRIVATE_TOKEN` 都未配置，health 会返回非 200。
4. 用单条抖音链接提交一个小任务，确认任务状态从 `queued` 进入执行并生成文件。
5. 文件只应从 `/downloads/api/jobs/{job_id}/files/...` 下载，服务本身不应暴露公网端口。

## 回滚

如果只需要停止面板服务，不改 Caddy：

```powershell
docker compose -f deploy/private-panel/docker-compose.yml down
```

如果已经修改了 Caddyfile，先恢复 Caddy 中 `/downloads` 相关片段，再运行 Caddy 配置校验和 reload。生产部署和 Caddy reload 需要单独确认后再执行。
