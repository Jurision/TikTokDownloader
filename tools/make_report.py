"""
把 fetch_comments.py 产出的 JSON 渲染成一个自包含 HTML 报告。

用法:
    python tools/make_report.py <comments-*.json> [--out 路径] [--format standalone|artifact]

    standalone  完整 HTML 文档，双击就能在浏览器里看（默认）
    artifact    去掉 doctype/html/head/body 外壳，供发布成 Artifact
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Noto+Sans+SC:wght@400;500;700&"
    'family=IBM+Plex+Mono:wght@400;500;600&display=swap">'
)

CSS = """
:root{
  --paper:#F5F8F8; --surface:#FFFFFF; --sunken:#EDF2F3;
  --ink:#0F1719; --ink-2:#3A4C51; --muted:#6B8085; --line:#DDE6E7;
  --accent:#0E7C86; --accent-soft:#D3EBED; --warm:#A45E06; --warm-soft:#F6E7CF;
  --shadow:0 1px 2px rgba(15,23,25,.05),0 8px 24px -16px rgba(15,23,25,.25);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#0C1214; --surface:#141D20; --sunken:#0F181A;
    --ink:#E7EFF0; --ink-2:#B4C6CA; --muted:#7E969B; --line:#243135;
    --accent:#46B9C3; --accent-soft:#123239; --warm:#D9A05B; --warm-soft:#33240F;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -16px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --paper:#0C1214; --surface:#141D20; --sunken:#0F181A;
  --ink:#E7EFF0; --ink-2:#B4C6CA; --muted:#7E969B; --line:#243135;
  --accent:#46B9C3; --accent-soft:#123239; --warm:#D9A05B; --warm-soft:#33240F;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -16px rgba(0,0,0,.8);
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:"Noto Sans SC",-apple-system,"Microsoft YaHei",sans-serif;
  font-size:15px; line-height:1.65; -webkit-font-smoothing:antialiased;
}
.mono{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace;font-variant-numeric:tabular-nums}
.wrap{max-width:940px;margin:0 auto;padding:32px 20px 72px}

header{border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:24px}
.eyebrow{
  font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);margin:0 0 6px
}
h1{font-size:26px;line-height:1.25;margin:0 0 10px;text-wrap:balance;font-weight:700}
.meta{color:var(--muted);font-size:13px;display:flex;flex-wrap:wrap;gap:6px 16px;margin:0}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:24px}
.stat{background:var(--surface);padding:14px 16px}
.stat dt{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0 0 4px;
  font-family:"IBM Plex Mono",monospace}
.stat dd{margin:0;font-size:24px;font-weight:600;font-family:"IBM Plex Mono",monospace;
  font-variant-numeric:tabular-nums;line-height:1.1}
.stat dd small{font-size:12px;font-weight:400;color:var(--muted);margin-left:3px}

.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-bottom:28px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px 18px;box-shadow:var(--shadow)}
.card h2{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);
  margin:0 0 12px;font-family:"IBM Plex Mono",monospace;font-weight:500}
.bars{display:flex;flex-direction:column;gap:7px;margin:0}
.bar{display:grid;grid-template-columns:76px 1fr 38px;align-items:center;gap:10px;font-size:13px}
.bar-label{color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{height:8px;background:var(--sunken);border-radius:4px;overflow:hidden}
.bar-fill{height:100%;background:var(--accent);border-radius:4px}
.bar-num{text-align:right;color:var(--muted);font-family:"IBM Plex Mono",monospace;
  font-variant-numeric:tabular-nums;font-size:12px}

.toolbar{position:sticky;top:0;z-index:5;background:var(--paper);
  padding:12px 0;margin-bottom:4px;border-bottom:1px solid var(--line);
  display:flex;flex-wrap:wrap;gap:10px;align-items:center}
input[type=search]{flex:1;min-width:180px;padding:8px 12px;font:inherit;font-size:14px;
  background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:7px}
input[type=search]::placeholder{color:var(--muted)}
button{font:inherit;font-size:13px;padding:8px 13px;border-radius:7px;cursor:pointer;
  background:var(--surface);color:var(--ink-2);border:1px solid var(--line)}
button[aria-pressed=true]{background:var(--accent-soft);color:var(--accent);border-color:var(--accent)}
button.primary{background:var(--accent);color:var(--surface);border-color:var(--accent);font-weight:500}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.count{color:var(--muted);font-size:13px;font-family:"IBM Plex Mono",monospace}

.stream{list-style:none;margin:0;padding:0}
.item{padding:16px 0;border-bottom:1px solid var(--line)}
.item.hide{display:none}
.head{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;margin-bottom:5px}
.nick{font-weight:500;color:var(--ink)}
.chip{font-size:11px;padding:1px 7px;border-radius:20px;background:var(--sunken);
  color:var(--muted);font-family:"IBM Plex Mono",monospace}
.time{font-size:12px;color:var(--muted);font-family:"IBM Plex Mono",monospace;margin-left:auto}
.text{margin:0;color:var(--ink);white-space:pre-wrap;overflow-wrap:anywhere}
.foot{display:flex;gap:14px;align-items:center;margin-top:7px;font-size:12px;
  color:var(--muted);font-family:"IBM Plex Mono",monospace}
.digg{color:var(--warm);background:var(--warm-soft);padding:1px 8px;border-radius:20px;font-weight:500}
.digg.zero{color:var(--muted);background:var(--sunken);font-weight:400}
.replies{list-style:none;margin:12px 0 0;padding:0 0 0 16px;border-left:2px solid var(--line);
  display:flex;flex-direction:column;gap:12px}
.reply .text{font-size:14px;color:var(--ink-2)}
.empty{padding:40px 0;text-align:center;color:var(--muted)}
footer{margin-top:36px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12px}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

JS = """
(function(){
  var stream=document.getElementById('stream'), items=[].slice.call(stream.children);
  var q=document.getElementById('q'), cnt=document.getElementById('cnt');
  var byDigg=document.getElementById('by-digg'), byTime=document.getElementById('by-time');

  function refresh(){
    var t=q.value.trim().toLowerCase(), n=0;
    items.forEach(function(el){
      var hit=!t||el.dataset.search.indexOf(t)>-1;
      el.classList.toggle('hide',!hit); if(hit)n++;
    });
    cnt.textContent=n+' / '+items.length+' 条';
  }
  function sort(key,btn){
    byDigg.setAttribute('aria-pressed',btn===byDigg);
    byTime.setAttribute('aria-pressed',btn===byTime);
    items.slice().sort(function(a,b){return (+b.dataset[key])-(+a.dataset[key])})
         .forEach(function(el){stream.appendChild(el)});
  }
  q.addEventListener('input',refresh);
  byDigg.addEventListener('click',function(){sort('digg',byDigg)});
  byTime.addEventListener('click',function(){sort('ts',byTime)});

  document.getElementById('copy').addEventListener('click',function(b){
    var self=this;
    navigator.clipboard.writeText(document.getElementById('digest').textContent).then(function(){
      var o=self.textContent; self.textContent='已复制';
      setTimeout(function(){self.textContent=o},1600);
    },function(){ self.textContent='复制失败，手动选中下方文本'; });
  });
  refresh();
})();
"""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def num(v) -> int:
    try:
        return max(int(v), 0)
    except (TypeError, ValueError):
        return 0


def bars(counter: Counter, limit: int = 8) -> str:
    if not counter:
        return '<p class="empty">无数据</p>'
    top = counter.most_common(limit)
    hi = top[0][1] or 1
    out = ['<dl class="bars">']
    for label, n in top:
        pct = round(n / hi * 100, 1)
        out.append(
            f'<div class="bar"><dt class="bar-label">{esc(label or "未知")}</dt>'
            f'<dd class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></dd>'
            f'<dd class="bar-num">{n}</dd></div>'
        )
    out.append("</dl>")
    return "".join(out)


def render(records: list[dict], fmt: str) -> str:
    rec = records[0]
    comments = rec["comments"]
    replies = rec.get("replies") or {}

    for c in comments:
        c["_d"] = num(c.get("digg_count"))
    total_digg = sum(c["_d"] for c in comments)
    n_reply = sum(len(v) for v in replies.values())

    ip = Counter((c.get("ip_label") or "未知") for c in comments)
    hours = Counter((c.get("create_time") or "")[11:13] for c in comments if c.get("create_time"))
    times = sorted(c["create_time"] for c in comments if c.get("create_time"))

    # ---- 评论流 ----
    rows = []
    for c in sorted(comments, key=lambda x: -x["_d"]):
        rs = replies.get(c["cid"]) or []
        blob = f"{c.get('text','')} {c.get('nickname','')} {c.get('ip_label','')}".lower()
        rhtml = ""
        if rs:
            parts = []
            for r in rs:
                parts.append(
                    f'<li class="reply"><div class="head">'
                    f'<span class="nick">{esc(r.get("nickname"))}</span>'
                    f'<span class="chip">{esc(r.get("ip_label") or "未知")}</span>'
                    f'<span class="time">{esc(r.get("create_time"))}</span></div>'
                    f'<p class="text">{esc(r.get("text"))}</p></li>'
                )
            rhtml = f'<ul class="replies">{"".join(parts)}</ul>'
            blob += " " + " ".join((r.get("text") or "").lower() for r in rs)

        d = c["_d"]
        rows.append(
            f'<li class="item" data-digg="{d}" data-ts="{esc(c.get("create_timestamp") or 0)}" '
            f'data-search="{esc(blob)}">'
            f'<div class="head"><span class="nick">{esc(c.get("nickname"))}</span>'
            f'<span class="chip">{esc(c.get("ip_label") or "未知")}</span>'
            f'<span class="time">{esc(c.get("create_time"))}</span></div>'
            f'<p class="text">{esc(c.get("text"))}</p>'
            f'<div class="foot"><span class="digg{"" if d else " zero"}">{d} 赞</span>'
            f'<span>{num(c.get("reply_comment_total"))} 回复</span></div>'
            f"{rhtml}</li>"
        )

    # ---- 给 AI 的纯文本摘要 ----
    lines = [
        f"{rec.get('platform') or '抖音'}作品 {rec['detail_id']} 评论数据",
        f"采集于 {rec['collected_at']}，共 {len(comments)} 条评论"
        + (f"、{n_reply} 条二级回复" if n_reply else ""),
        f"时间跨度 {times[0] if times else '?'} ~ {times[-1] if times else '?'}",
        f"IP 分布：{'、'.join(f'{k} {v}' for k, v in ip.most_common())}",
        "",
        "格式：[赞数] 昵称(IP) 评论时间 内容",
        "",
    ]
    for c in sorted(comments, key=lambda x: -x["_d"]):
        lines.append(
            f"[{c['_d']}] {c.get('nickname')}({c.get('ip_label') or '未知'}) "
            f"{c.get('create_time')} {c.get('text')}"
        )
        for r in replies.get(c["cid"]) or []:
            lines.append(
                f"    └ {r.get('nickname')}({r.get('ip_label') or '未知'}) "
                f"{r.get('create_time')} {r.get('text')}"
            )
    digest = "\n".join(lines)

    span = f"{times[0][5:16]} → {times[-1][5:16]}" if times else "—"
    platform = rec.get("platform") or "抖音"
    title = f"作品 {rec['detail_id']} 评论区"

    body = f"""<div class="wrap">
<header>
  <p class="eyebrow">{esc(platform)} 评论采集</p>
  <h1>作品 {esc(rec['detail_id'])} 的评论区</h1>
  <p class="meta"><span class="mono">采集于 {esc(str(rec['collected_at']).replace('T', ' '))}</span>
  <span>来源 {esc(rec.get('source_url'))}</span></p>
</header>

<dl class="stats">
  <div class="stat"><dt>评论</dt><dd>{len(comments)}</dd></div>
  <div class="stat"><dt>二级回复</dt><dd>{n_reply}</dd></div>
  <div class="stat"><dt>总点赞</dt><dd>{total_digg}</dd></div>
  <div class="stat"><dt>0 赞占比</dt>
    <dd>{round(sum(1 for c in comments if not c['_d']) / max(len(comments), 1) * 100)}<small>%</small></dd></div>
  <div class="stat"><dt>地区</dt><dd>{len(ip)}</dd></div>
</dl>

<div class="charts">
  <section class="card"><h2>IP 归属地</h2>{bars(ip)}</section>
  <section class="card"><h2>发布时段 · {esc(span)}</h2>
    {bars(Counter({f"{h}:00": n for h, n in sorted(hours.items())}), 24)}</section>
</div>

<div class="toolbar">
  <input type="search" id="q" placeholder="搜索评论内容、昵称、地区…" aria-label="搜索评论">
  <button id="by-digg" aria-pressed="true">按点赞</button>
  <button id="by-time" aria-pressed="false">按时间</button>
  <button id="copy" class="primary">复制给 AI</button>
  <span class="count" id="cnt"></span>
</div>

<ul class="stream" id="stream">{"".join(rows)}</ul>

<footer>
  <p>由 DouK-Downloader 采集 · 报告生成于 {esc(datetime.now().strftime("%Y-%m-%d %H:%M"))}</p>
  <pre id="digest" hidden>{esc(digest)}</pre>
</footer>
</div>"""

    head = f"<title>{esc(title)}</title>{FONTS}<style>{CSS}</style>"
    doc = f"{head}{body}<script>{JS}</script>"

    if fmt == "artifact":
        return doc
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"{head}</head><body>{body}<script>{JS}</script></body></html>"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file")
    ap.add_argument("--out")
    ap.add_argument("--format", choices=("standalone", "artifact"), default="standalone")
    args = ap.parse_args()

    src = Path(args.json_file)
    records = json.loads(src.read_text(encoding="utf-8"))
    if not records:
        print("JSON 里没有数据", file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else src.with_suffix(".html")
    out.write_text(render(records, args.format), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
