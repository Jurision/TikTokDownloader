"""
一条链接 → 评论全量抓取，输出 JSON（供 AI 分析）+ CSV（程序自带）。
抖音与 TikTok 均支持，按链接域名自动分流。

用法:
    python tools/fetch_comments.py <链接或作品ID> [更多链接...] [选项]

    --reply       同时抓二级回复（有回复的评论逐条拉，会慢很多）
    --pages N     最多翻 N 页，一页 20 条；不给则抓完为止
    --tiktok      只给作品 ID 时强制按 TikTok 处理（给链接则自动判断）
    --delay S     拉回复时每条间隔秒数，默认抖音 1.0 / TikTok 2.5
    --salvage ID  不采集，把上次被硬杀后残留的检查点转成结果 JSON

中断不会丢数据：Ctrl+C 会把在飞请求里已累积的部分抢救出来正常落盘
（结果标 "partial": true）；被硬杀（超时 kill、断电）则靠每 20 页写一次的
检查点，事后用 --salvage <作品ID> 取回。

复用程序自身的 Parameter / Comment / Extractor，不重复实现签名逻辑。
Cookie 从 Volume/settings.json 读，脚本不接触也不打印它。

进度打在 stderr 上，原地刷新一行（翻页阶段报页数与累计条数，
回复阶段报第几条/共几条）。要把进度和结果分开，重定向 stdout 即可。

注意 TikTok 对高频请求敏感：回复是逐条请求的，无节流会很快被限流，
表现为「响应内容不是有效的 JSON 数据」。连续 3 条失败会自动停止回复采集。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.application import TikTokDownloader  # noqa: E402
from src.application.main_terminal import TikTok  # noqa: E402
from src.interface import Comment  # noqa: E402

OUT_DIR = ROOT / "Volume" / "reports"

# 翻页进度是否逐页打印。拉二级回复时关掉，否则几十条回复会刷屏，
# 那一阶段由 collect() 自己打一行汇总进度。
SHOW_PAGES = True

# 每翻多少页写一次检查点。硬杀（超时 kill、断电）时靠它保住已采数据。
CKPT_EVERY = 20

# 当前在飞的请求，供中断时抢救。{"api": API 实例, "detail_id": str}
_LIVE: dict = {}


def ckpt_path(detail_id: str) -> Path:
    return OUT_DIR / f".ckpt-{detail_id}.json"


def write_ckpt(detail_id: str, raw: list[dict]) -> None:
    """原子写：先写 .tmp 再 replace，避免写一半被杀留下坏文件。"""
    if not raw:
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = ckpt_path(detail_id)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def drop_ckpt(detail_id: str) -> None:
    ckpt_path(detail_id).unlink(missing_ok=True)


class PageProgress:
    """
    接管上游的 rich 进度条。

    上游 API.run() 的翻页循环每页调一次 progress.update()，但它建的 task
    是 total=None 的纯 spinner，看不出进度。这里换成能读真实计数的版本：
    self.response 是逐条累加的，len() 就是当前已获取条数。

    走的是 template.py::progress_object() 里预留的 _progress_factory 钩子，
    不改上游代码。
    """

    def __init__(self, api):
        self.api = api
        self.label = ""
        self.pages = 0
        self.last = 0.0
        # 登记在飞的请求，中断时 collect() 靠它把已采部分抢救出来
        _LIVE["api"] = api

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if SHOW_PAGES and self.pages:
            print(f"\r   {self.label} 共 {self.pages} 页 / "
                  f"{len(self.api.response)} 条{' ' * 20}", file=sys.stderr)
        return False

    def add_task(self, description="", total=None, **kwargs):
        self.label = description
        return 0

    def update(self, task_id=0, **kwargs):
        self.pages += 1

        # 定期落检查点，防硬杀
        did = _LIVE.get("detail_id")
        if did and SHOW_PAGES and self.pages % CKPT_EVERY == 0:
            write_ckpt(did, self.api.response)

        if not SHOW_PAGES:
            return
        now = time.monotonic()
        # 限流到每 0.5s 一次，避免刷屏；首页和每 10 页必打
        if now - self.last < 0.5 and self.pages % 10:
            return
        self.last = now
        print(f"\r   {self.label} 第 {self.pages} 页 / "
              f"已取 {len(self.api.response)} 条", end="", file=sys.stderr,
              flush=True)


def _factory(self):
    return PageProgress(self)


# Reply 继承自 Comment，CommentTikTok/ReplyTikTok 也在这条链上，挂一处即可
Comment._progress_factory = _factory


def is_tiktok(url: str) -> bool:
    return "tiktok.com" in url.lower()


async def collect(
    urls: list[str],
    reply: bool,
    pages: int | None,
    force_tiktok: bool = False,
    delay: float | None = None,
) -> list[dict]:
    results = []
    async with TikTokDownloader() as app:
        app.check_config()
        await app.check_settings(False)

        tk = TikTok(app.parameter, app.database)

        for url in urls:
            tiktok = force_tiktok or is_tiktok(url)
            platform = "TikTok" if tiktok else "抖音"

            state = (
                app.parameter.cookie_tiktok_state if tiktok
                else app.parameter.cookie_state
            )
            if not state:
                key = "cookie_tiktok" if tiktok else "cookie"
                print(f"!! {platform} Cookie 未设置或已失效"
                      f"（settings.json 的 {key}）", file=sys.stderr)
                continue

            if url.strip().isdigit():
                ids = [url.strip()]          # 直接给的作品 ID
            else:
                link = tk.links_tiktok if tiktok else tk.links
                ids = [i for i in await link.run(url) if i]
            if not ids:
                print(f"!! 无法从 {url} 提取作品 ID", file=sys.stderr)
                continue

            get_comments = (
                tk.comment_handle_single_tiktok if tiktok
                else tk.comment_handle_single
            )
            get_replies = tk.reply_handle_tiktok if tiktok else tk.reply_handle

            for detail_id in ids:
                print(f".. [{platform}] 采集 {detail_id}", file=sys.stderr)
                kwargs = {"pages": pages} if pages else {}
                _LIVE["detail_id"] = detail_id
                _LIVE.pop("api", None)
                partial = False

                try:
                    comments = await get_comments(detail_id, **kwargs)
                except (KeyboardInterrupt, asyncio.CancelledError):
                    # Ctrl+C：把在飞请求里已累积的原始数据抢救出来
                    comments = await salvage(tk, detail_id)
                    partial = True
                    print(f"\n!! 已中断，抢救出 {len(comments)} 条评论",
                          file=sys.stderr)

                if not comments:
                    print(f"!! {detail_id} 没采到评论", file=sys.stderr)
                    continue

                replies: dict[str, list] = {}
                if reply and not partial:
                    targets = [
                        c for c in comments
                        if int(c.get("reply_comment_total") or 0) > 0
                    ]
                    # 回复要逐条请求，不节流会被限流（TikTok 尤其敏感）
                    gap = delay if delay is not None else (2.5 if tiktok else 1.0)
                    print(f".. 拉 {len(targets)} 条评论的回复"
                          f"（每条间隔 {gap}s）", file=sys.stderr)
                    misses = 0
                    global SHOW_PAGES
                    SHOW_PAGES = False
                    try:
                        for n, c in enumerate(targets):
                            if n:
                                await asyncio.sleep(gap)
                            print(f"\r   回复 {n + 1}/{len(targets)} / "
                                  f"已取 {sum(len(v) for v in replies.values())} 条",
                                  end="", file=sys.stderr, flush=True)
                            got = await get_replies(detail_id, c["cid"], **kwargs)
                            if got:
                                replies[c["cid"]] = got
                                misses = 0
                            else:
                                misses += 1
                                # 连续失败多半是被限流了，继续打只会更糟
                                if misses >= 3:
                                    print("!! 连续 3 条回复拉取失败，判定为限流，"
                                          "停止回复采集（已拿到的评论仍会保留）",
                                          file=sys.stderr)
                                    break
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        partial = True
                        print(f"\n!! 已中断，保留已拉到的 "
                              f"{sum(len(v) for v in replies.values())} 条回复",
                              file=sys.stderr)
                    finally:
                        SHOW_PAGES = True
                        print(file=sys.stderr)

                results.append({
                    "platform": platform,
                    "source_url": url,
                    "detail_id": detail_id,
                    "collected_at": datetime.now().isoformat(timespec="seconds"),
                    "partial": partial,
                    "comment_count": len(comments),
                    "reply_count": sum(len(v) for v in replies.values()),
                    "comments": comments,
                    "replies": replies,
                })
                # 数据已进 results，正常落盘即可，检查点不再需要
                drop_ckpt(detail_id)
                if partial:
                    return results      # 用户已要求中断，不再继续后面的作品
    return results


async def salvage(tk: TikTok, detail_id: str) -> list[dict]:
    """把在飞请求里累积的原始数据过一遍提取器，得到和正常路径一样的结构。"""
    api = _LIVE.get("api")
    raw = list(api.response) if api is not None else []
    if not raw:
        raw = read_ckpt(detail_id)
    if not raw:
        return []
    return await tk.save_comment(detail_id, raw)


def read_ckpt(detail_id: str) -> list[dict]:
    p = ckpt_path(detail_id)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


async def salvage_only(detail_id: str) -> list[dict]:
    """--salvage：把硬杀后残留的检查点转成正常的结果 JSON。"""
    raw = read_ckpt(detail_id)
    if not raw:
        print(f"!! 没有 {detail_id} 的检查点", file=sys.stderr)
        return []
    async with TikTokDownloader() as app:
        app.check_config()
        await app.check_settings(False)
        tk = TikTok(app.parameter, app.database)
        comments = await tk.save_comment(detail_id, raw)
    if not comments:
        return []
    drop_ckpt(detail_id)
    return [{
        "platform": "抖音",
        "source_url": f"(从检查点恢复) {detail_id}",
        "detail_id": detail_id,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "partial": True,
        "comment_count": len(comments),
        "reply_count": 0,
        "comments": comments,
        "replies": {},
    }]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*", help="抖音作品链接或作品 ID")
    ap.add_argument("--salvage", metavar="作品ID",
                    help="不采集，把上次被硬杀后残留的检查点转成结果 JSON")
    ap.add_argument("--reply", action="store_true", help="同时抓二级回复")
    ap.add_argument("--pages", type=int, default=None, help="最多翻几页（一页 20 条）")
    ap.add_argument("--tiktok", action="store_true",
                    help="强制按 TikTok 处理（只给作品 ID 时用，链接会自动判断）")
    ap.add_argument("--delay", type=float, default=None,
                    help="拉二级回复时每条之间的间隔秒数，"
                         "默认抖音 1.0、TikTok 2.5")
    args = ap.parse_args()

    if args.salvage:
        results = asyncio.run(salvage_only(args.salvage))
    elif not args.urls:
        ap.error("要么给链接/作品 ID，要么用 --salvage")
    else:
        try:
            results = asyncio.run(
                collect(args.urls, args.reply, args.pages,
                        args.tiktok, args.delay)
            )
        except KeyboardInterrupt:
            # collect 内部已尽量抢救；这里兜住它自己来不及处理的情况
            print("\n!! 已中断", file=sys.stderr)
            results = []
    if not results:
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"comments-{stamp}.json"
    out.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for r in results:
        tag = "部分" if r.get("partial") else "OK"
        line = (f"{tag} [{r['platform']}] {r['detail_id']}: "
                f"{r['comment_count']} 条评论")
        if r["reply_count"]:
            line += f" + {r['reply_count']} 条回复"
        print(line)
    print(f"JSON: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
