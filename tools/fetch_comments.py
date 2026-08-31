"""
一条链接 → 评论全量抓取，输出 JSON（供 AI 分析）+ CSV（程序自带）。
抖音与 TikTok 均支持，按链接域名自动分流。

用法:
    python tools/fetch_comments.py <链接或作品ID> [更多链接...] [选项]

    --reply       同时抓二级回复（有回复的评论逐条拉，会慢很多）
    --pages N     最多翻 N 页，一页 20 条；不给则抓完为止
    --tiktok      只给作品 ID 时强制按 TikTok 处理（给链接则自动判断）
    --delay S     拉回复时每条间隔秒数，默认抖音 1.0 / TikTok 2.5

复用程序自身的 Parameter / Comment / Extractor，不重复实现签名逻辑。
Cookie 从 Volume/settings.json 读，脚本不接触也不打印它。

注意 TikTok 对高频请求敏感：回复是逐条请求的，无节流会很快被限流，
表现为「响应内容不是有效的 JSON 数据」。连续 3 条失败会自动停止回复采集。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.application import TikTokDownloader  # noqa: E402
from src.application.main_terminal import TikTok  # noqa: E402

OUT_DIR = ROOT / "Volume" / "reports"


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
                comments = await get_comments(detail_id, **kwargs)
                if not comments:
                    print(f"!! {detail_id} 没采到评论", file=sys.stderr)
                    continue

                replies: dict[str, list] = {}
                if reply:
                    targets = [
                        c for c in comments
                        if int(c.get("reply_comment_total") or 0) > 0
                    ]
                    # 回复要逐条请求，不节流会被限流（TikTok 尤其敏感）
                    gap = delay if delay is not None else (2.5 if tiktok else 1.0)
                    print(f".. 拉 {len(targets)} 条评论的回复"
                          f"（每条间隔 {gap}s）", file=sys.stderr)
                    misses = 0
                    for n, c in enumerate(targets):
                        if n:
                            await asyncio.sleep(gap)
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

                results.append({
                    "platform": platform,
                    "source_url": url,
                    "detail_id": detail_id,
                    "collected_at": datetime.now().isoformat(timespec="seconds"),
                    "comment_count": len(comments),
                    "reply_count": sum(len(v) for v in replies.values()),
                    "comments": comments,
                    "replies": replies,
                })
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="+", help="抖音作品链接或作品 ID")
    ap.add_argument("--reply", action="store_true", help="同时抓二级回复")
    ap.add_argument("--pages", type=int, default=None, help="最多翻几页（一页 20 条）")
    ap.add_argument("--tiktok", action="store_true",
                    help="强制按 TikTok 处理（只给作品 ID 时用，链接会自动判断）")
    ap.add_argument("--delay", type=float, default=None,
                    help="拉二级回复时每条之间的间隔秒数，"
                         "默认抖音 1.0、TikTok 2.5")
    args = ap.parse_args()

    results = asyncio.run(
        collect(args.urls, args.reply, args.pages, args.tiktok, args.delay)
    )
    if not results:
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"comments-{stamp}.json"
    out.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for r in results:
        line = f"OK [{r['platform']}] {r['detail_id']}: {r['comment_count']} 条评论"
        if r["reply_count"]:
            line += f" + {r['reply_count']} 条回复"
        print(line)
    print(f"JSON: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
