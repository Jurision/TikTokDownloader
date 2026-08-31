"""
把剪贴板里的抖音 Cookie 写进本 worktree 的 Volume/settings.json。

从 stdin 读，容错以下几种复制结果：
  1. 纯 Cookie 串            ttwid=1%7C...; sessionid=...; ...
  2. 带 header 名的            Cookie: ttwid=1%7C...; ...
  3. DevTools「复制为 cURL」   curl 'https://...' -H 'cookie: ttwid=...' ...
  4. 多行 header 块            Accept: ...\nCookie: ...\n...

会校验登录态字段是否存在；**从不打印 Cookie 内容本身**，只报字段名。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SETTINGS = Path(__file__).resolve().parent.parent / "Volume" / "settings.json"
ENCODE = "UTF-8-SIG"

# 有其一即为登录态
SESSION_KEYS = ("sessionid", "sessionid_ss", "sid_tt")
# 采集还依赖的设备/风控字段，缺了大概率被风控
DEVICE_KEYS = ("ttwid", "odin_tt", "passport_csrf_token")
TIKTOK_DEVICE_KEYS = ("ttwid", "msToken", "tt_csrf_token")


def extract(raw: str) -> str:
    raw = raw.strip()

    # 3. cURL：-H 'cookie: xxx' / -H "Cookie: xxx" / -b 'xxx'
    m = re.search(
        r"""-H\s+(['"])\s*cookie\s*:\s*(?P<v>.*?)\1""", raw, re.IGNORECASE | re.DOTALL
    )
    if m:
        return m.group("v").strip()
    m = re.search(r"""-b\s+(['"])(?P<v>.*?)\1""", raw, re.DOTALL)
    if m:
        return m.group("v").strip()

    # 4. 多行 header 块里挑出 Cookie 行
    for line in raw.splitlines():
        if re.match(r"^\s*cookie\s*:", line, re.IGNORECASE):
            return line.split(":", 1)[1].strip()

    # 2. 单行带 header 名
    if re.match(r"^\s*cookie\s*:", raw, re.IGNORECASE):
        return raw.split(":", 1)[1].strip()

    # 1. 当作纯 Cookie 串
    return raw


def looks_like_url(text: str) -> bool:
    head = text.split("=", 1)[0]
    return text.startswith(("http://", "https://", "/")) or "?" in head


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiktok", action="store_true",
                    help="写入 cookie_tiktok 而不是 cookie")
    args = ap.parse_args()
    field = "cookie_tiktok" if args.tiktok else "cookie"
    platform = "TikTok" if args.tiktok else "抖音"

    raw = sys.stdin.read()
    if not raw.strip():
        print("剪贴板是空的。先去 DevTools 复制 Cookie 值再跑。")
        return 2

    cookie = extract(raw)

    if looks_like_url(cookie):
        print("剪贴板里是一个 URL / 查询串，不是 Cookie。")
        print("你多半右键点了左边『名称』列表里的请求。要点的是右边")
        print("『请求标头』区域里 Cookie 那一行 → 右键 → 复制值。")
        return 3

    if "=" not in cookie or ";" not in cookie:
        print(f"内容不像 Cookie（长度 {len(cookie)}，没有 `key=value; ` 结构）。")
        return 3

    names = {p.split("=", 1)[0].strip() for p in cookie.split(";") if "=" in p}

    found_session = [k for k in SESSION_KEYS if k in names]
    if not found_session:
        print(f"解析出 {len(names)} 个字段，但没有登录态字段 "
              f"({'/'.join(SESSION_KEYS)})。")
        print("说明复制时页面未登录，或只复制到了 Cookie 的一部分。")
        return 4

    expect = TIKTOK_DEVICE_KEYS if args.tiktok else DEVICE_KEYS
    missing_device = [k for k in expect if k not in names]

    data = json.loads(SETTINGS.read_text(encoding=ENCODE))
    data[field] = cookie
    SETTINGS.write_text(
        json.dumps(data, ensure_ascii=False, indent=4), encoding=ENCODE
    )

    print(f"已写入 {SETTINGS} 的 {field}（{platform}）")
    print(f"  字段数    : {len(names)}")
    print(f"  登录态    : {', '.join(found_session)}")
    print(f"  风控字段  : {'齐全' if not missing_device else '缺 ' + ', '.join(missing_device)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
