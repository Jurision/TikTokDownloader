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

    # 1. 已经是干净的单行 Cookie 串就原样返回，避免被下面的兜底切短
    #    （Cookie 值里若含字面空格，正则会在空格处断开）
    if "\n" not in raw and ";" in raw and "=" in raw:
        return raw

    # 5. 兜底：从任意文本里捞出最长的一段 `k=v; k=v; ...`
    #    覆盖「复制为 cURL (cmd)」的 ^" 转义、PowerShell 格式等奇形怪状
    runs = re.findall(
        r"(?:[A-Za-z0-9_.-]+=[^;\s]*;\s*){2,}[A-Za-z0-9_.-]+=[^;\s]*", raw
    )
    if runs:
        return max(runs, key=len).strip()

    # 1. 当作纯 Cookie 串
    return raw


def describe(text: str) -> str:
    """安全地描述剪贴板内容的形状，不泄露值本身。"""
    keys = re.findall(r"([A-Za-z0-9_.-]+)=", text)
    bits = [
        f"长度 {len(text)}",
        f"{len(text.splitlines())} 行",
        f"{text.count('=')} 个 =",
        f"{text.count(';')} 个 ;",
    ]
    if keys:
        shown = "、".join(keys[:4])
        bits.append(f"字段名看起来是：{shown}" + ("…" if len(keys) > 4 else ""))
    else:
        bits.append("没有任何 key=value 结构")
    return "  ".join(bits)


def looks_like_url(text: str) -> bool:
    head = text.split("=", 1)[0]
    if text.startswith(("http://", "https://", "/")) or "?" in head:
        return True
    # 没带协议头的链接，例如 www.tiktok.com/@user/video/712...
    return bool(re.match(r"^(?:www\.)?[a-z0-9-]+\.[a-z]{2,}/", text, re.IGNORECASE))


def is_opaque_token(text: str) -> bool:
    """看着像一段高熵凭证（纯十六进制/base64），回显它有泄露风险。"""
    return bool(re.fullmatch(r"[A-Za-z0-9_%+/.-]{16,}={0,2}", text)) and not any(
        c in text for c in "/ "
    )


def from_browser(browser: str, domain: str) -> tuple[str, str]:
    """直接读浏览器 Cookie 库，绕开 DevTools 复制。返回 (cookie 串, 错误说明)。"""
    try:
        import rookiepy
    except ImportError:
        return "", "rookiepy 未安装：uv pip install rookiepy"

    getter = getattr(rookiepy, browser.lower(), None)
    if getter is None:
        return "", f"不支持的浏览器：{browser}"
    try:
        items = getter(domains=[domain])
    except Exception as error:  # noqa: BLE001
        return "", f"{browser} 读取失败：{error}"

    pairs = [
        f"{i['name']}={i['value']}"
        for i in items
        if i.get("name") and i.get("value")
    ]
    if not pairs:
        return "", f"{browser} 里没有 {domain} 的 Cookie（可能没在该浏览器登录）"
    return "; ".join(pairs), ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiktok", action="store_true",
                    help="写入 cookie_tiktok 而不是 cookie")
    ap.add_argument("--browser", metavar="NAME",
                    help="直接从浏览器读取（firefox / chrome / edge / brave …），"
                         "不走剪贴板。Chrome 系 v130+ 需管理员权限，Firefox 无此限制")
    args = ap.parse_args()
    field = "cookie_tiktok" if args.tiktok else "cookie"
    platform = "TikTok" if args.tiktok else "抖音"
    domain = "tiktok.com" if args.tiktok else "douyin.com"

    if args.browser:
        cookie, err = from_browser(args.browser, domain)
        if err:
            print(err)
            return 5
    else:
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
        print("内容不像 Cookie —— 完整的 Cookie 是几十段 `key=value;` 拼起来的长串。")
        print(f"  实际拿到：{describe(cookie)}")
        if is_opaque_token(cookie):
            print("  内容看着像单个凭证值，为避免泄露不予回显。")
        else:
            print(f"  内容：{cookie}")
        print()
        print("最可能的原因：在 DevTools 的 Cookie 表格里右键了某一行，")
        print("那只会复制单个值。要的是整条 Cookie 请求头，两种拿法：")
        print("  A. 左边『名称』列表里右键那条请求 → 复制 → 复制为 cURL(bash)")
        print("  B. 右边『标头』→『请求标头』里 Cookie 那一行 → 右键 → 复制值")
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
