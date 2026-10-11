"""
从「征集片单」类评论区里统计被推荐的影片，输出可视化页面。

用法:
    python tools/movie_report.py <检查点或结果 JSON> [--out 路径] [--format standalone|artifact]

两种输入都吃：
  - Volume/reports/.ckpt-<作品ID>.json   采集途中的原始检查点（可边跑边看）
  - Volume/reports/comments-*.json       采集完成的结果

片名识别是自举的，不写死片单：
  1. 先把所有写在《》里的片名收集起来，出现 >= 2 次的进候选集
  2. 再拿候选集去全文扫一遍，把裸写的（没加书名号的）也计上
  3. 同一条评论里若「给阿嬷的情书」命中，就不再把「情书」也记一次，
     避免子串重复计数
"""

from __future__ import annotations

import argparse
import collections
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# 常被裸写、未必有人加书名号的，作为候选集的补充种子
SEED = [
    "怦然心动", "放牛班的春天", "肖申克的救赎", "海边的曼彻斯特", "那山那人那狗",
    "隐入尘烟", "岁月神偷", "幸福来敲门", "菊次郎的夏天", "海蒂和爷爷",
    "落叶归根", "完美的日子", "小森林", "海街日记", "步履不停", "比海更深",
    "忠犬八公", "海上钢琴师", "入殓师", "小鞋子", "天堂电影院", "绿皮书",
    "触不可及", "横道世之介", "山河故人", "桃姐", "天水围的日与夜", "一一",
]

# 同片异名 / 错字
ALIAS = {
    "给阿嫲的情书": "给阿嬷的情书", "给阿麽的情书": "给阿嬷的情书",
    "阿嬷的情书": "给阿嬷的情书",
    "那人那山那狗": "那山那人那狗",
    "当幸福来敲门": "幸福来敲门",
    "本杰明巴顿奇事": "返老还童", "本杰明·巴顿奇事": "返老还童",
    "Flipped": "怦然心动",
}

GENRE = {
    "日系生活流": ["菊次郎的夏天", "小森林", "海街日记", "步履不停", "比海更深",
                   "横道世之介", "入殓师", "完美的日子", "无人知晓", "如父如子",
                   "情书", "深夜食堂", "小偷家族", "东京物语", "滨边的曼彻斯特"],
    "华语乡土年代": ["隐入尘烟", "那山那人那狗", "岁月神偷", "落叶归根", "山河故人",
                     "天水围的日与夜", "桃姐", "人生大事", "芙蓉镇", "活着", "一一",
                     "阳光普照", "钢的琴", "孔雀", "立春", "我的父亲母亲", "暖"],
    "欧美治愈": ["海蒂和爷爷", "触不可及", "绿皮书", "放牛班的春天", "幸福来敲门",
                 "海边的曼彻斯特", "心灵捕手", "天堂电影院", "闻香识女人", "美丽心灵",
                 "白日梦想家", "罗马假日", "廊桥遗梦", "返老还童"],
}


def canon(name: str) -> str:
    name = name.strip().strip("。，,.!！?？、：: ")
    name = re.sub(r"[（(][^）)]*[）)]$", "", name).strip()
    return ALIAS.get(name, name)


def load(path: Path) -> tuple[list[dict], str, bool]:
    """归一成 [{text, digg, nick, ip, ts}]，返回 (条目, 作品ID, 是否为途中快照)。"""
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, list) and data and "comments" in (data[0] or {}):
        rec = data[0]                       # 结果 JSON（已提取）
        out = [{
            "text": c.get("text") or "",
            "digg": max(int(c.get("digg_count") or 0), 0),
            "nick": c.get("nickname") or "",
            "ip": c.get("ip_label") or "未知",
            "ts": c.get("create_time") or "",
        } for c in rec["comments"]]
        for lst in (rec.get("replies") or {}).values():
            out += [{
                "text": r.get("text") or "",
                "digg": max(int(r.get("digg_count") or 0), 0),
                "nick": r.get("nickname") or "",
                "ip": r.get("ip_label") or "未知",
                "ts": r.get("create_time") or "",
            } for r in lst]
        return out, rec["detail_id"], bool(rec.get("partial"))

    # 原始检查点
    out = []
    for c in data:
        ts = c.get("create_time")
        out.append({
            "text": c.get("text") or "",
            "digg": max(int(c.get("digg_count") or 0), 0),
            "nick": (c.get("user") or {}).get("nickname") or "",
            "ip": c.get("ip_label") or "未知",
            "ts": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                  if isinstance(ts, int) else "",
        })
    did = str(data[0].get("aweme_id") or "") if data else ""
    return out, did, True


# 片名短于等于这个长度时，必须写在书名号里才算数。
# 「情书」「一一」「暖」「活着」这类撞常用词，裸写扫描会把
# 「唯一一部」「一封情书」全算进去。
STRICT_LEN = 2

BRACKET = re.compile(r"[《〈]([^》〉]{1,30})[》〉]")


def analyse(units: list[dict]):
    # 1. 自举候选集（书名号里出现 >= 2 次的，加种子）
    brack = collections.Counter()
    for u in units:
        for m in BRACKET.findall(u["text"]):
            brack[canon(m)] += 1
    cands = {k for k, v in brack.items() if v >= 2 and len(k) >= 2}
    cands |= {canon(s) for s in SEED}

    # 2. 裸写扫描用的表面形式 → 规范名。把别名的原始写法也放进去，
    #    否则「给阿嫲的情书」只会匹配上「情书」。
    surface: dict[str, str] = {c: c for c in cands if len(c) > STRICT_LEN}
    for raw, std in ALIAS.items():
        if std in cands and len(raw) > STRICT_LEN:
            surface[raw] = std

    films: dict[str, dict] = collections.defaultdict(
        lambda: {"n": 0, "digg": 0, "cites": []})
    for u in units:
        text = u["text"]
        # 书名号里的：任意长度都算
        hit_raw = {m for m in BRACKET.findall(text) if canon(m) in cands}
        # 裸写的：只认长片名
        hit_raw |= {s for s in surface if s in text}
        # 去子串污染：「给阿嬷的情书」命中时不再把「情书」也记一次
        hit_raw = {s for s in hit_raw if not any(s != o and s in o for o in hit_raw)}

        for name in {canon(s) for s in hit_raw}:
            f = films[name]
            f["n"] += 1
            f["digg"] += u["digg"]
            f["cites"].append(u)
    for f in films.values():
        f["cites"].sort(key=lambda x: -x["digg"])
    return films, brack


def genre_of(name: str) -> str:
    for g, names in GENRE.items():
        if name in names:
            return g
    return ""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Noto+Serif+SC:wght@500;700&family=Noto+Sans+SC:wght@400;500&"
    'family=IBM+Plex+Mono:wght@400;500&display=swap">'
)

CSS = """
:root{
  --paper:#F1F3EF; --surface:#FFFFFF; --sunken:#E7EBE4;
  --ink:#171A16; --ink-2:#3F473C; --muted:#6E776A; --line:#DCE1D6;
  --accent:#3D5A4C; --accent-soft:#DAE7DD; --hot:#8F5522; --hot-soft:#F4E5D4;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#0D100E; --surface:#161A17; --sunken:#11150F;
    --ink:#E9EEE7; --ink-2:#BCC6B8; --muted:#8B9587;
    --line:#252B24; --accent:#84B897; --accent-soft:#17291F;
    --hot:#D59B63; --hot-soft:#2E2113;
  }
}
:root[data-theme="dark"]{
  --paper:#0D100E; --surface:#161A17; --sunken:#11150F;
  --ink:#E9EEE7; --ink-2:#BCC6B8; --muted:#8B9587;
  --line:#252B24; --accent:#84B897; --accent-soft:#17291F;
  --hot:#D59B63; --hot-soft:#2E2113;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:"Noto Sans SC",-apple-system,"Microsoft YaHei",sans-serif;
  font-size:15px;line-height:1.7;-webkit-font-smoothing:antialiased}
.wrap{max-width:860px;margin:0 auto;padding:40px 20px 80px}

.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--muted);margin:0 0 10px}
h1{font-family:"Noto Serif SC",serif;font-weight:700;font-size:30px;line-height:1.3;
  margin:0 0 12px;text-wrap:balance}
.lede{color:var(--ink-2);margin:0 0 6px;max-width:60ch}
.src{color:var(--muted);font-size:13px;margin:0}
.live{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;
  background:var(--accent-soft);color:var(--accent);font-weight:500;margin-left:6px;
  font-family:"Noto Sans SC",sans-serif;vertical-align:middle}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line);border-radius:12px;
  overflow:hidden;margin:28px 0}
.stat{background:var(--surface);padding:14px 16px}
.stat dt{font-size:11px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);margin:0 0 3px;font-family:"IBM Plex Mono",monospace}
.stat dd{margin:0;font-size:23px;font-weight:500;line-height:1.1;
  font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}

.genres{display:flex;flex-direction:column;gap:8px;margin:0 0 30px}
.gr{display:grid;grid-template-columns:96px 1fr 44px;gap:12px;align-items:center;
  font-size:13px}
.gr-t{color:var(--ink-2);white-space:nowrap}
.gr-b{height:7px;background:var(--sunken);border-radius:4px;overflow:hidden}
.gr-f{height:100%;background:var(--accent);border-radius:4px}
.gr-n{text-align:right;color:var(--muted);font-family:"IBM Plex Mono",monospace;
  font-size:12px;font-variant-numeric:tabular-nums}

.bar{position:sticky;top:0;z-index:5;background:var(--paper);padding:12px 0;
  border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:9px;
  align-items:center;margin-bottom:6px}
input[type=search]{flex:1;min-width:170px;padding:8px 12px;font:inherit;font-size:14px;
  background:var(--surface);color:var(--ink);border:1px solid var(--line);
  border-radius:8px}
input[type=search]::placeholder{color:var(--muted)}
button{font:inherit;font-size:13px;padding:7px 13px;border-radius:8px;cursor:pointer;
  background:var(--surface);color:var(--ink-2);border:1px solid var(--line)}
button[aria-pressed=true]{background:var(--accent-soft);color:var(--accent);
  border-color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.cnt{color:var(--muted);font-size:13px;font-family:"IBM Plex Mono",monospace}

.list{list-style:none;margin:0;padding:0}
.film{border-bottom:1px solid var(--line)}
.film.hide{display:none}
.row{display:grid;grid-template-columns:42px 1fr auto;gap:14px;align-items:baseline;
  width:100%;background:none;border:none;padding:17px 2px;text-align:left;
  cursor:pointer;border-radius:0;color:inherit}
.row:hover .name{color:var(--accent)}
.rank{font-family:"IBM Plex Mono",monospace;font-size:14px;color:var(--muted);
  font-variant-numeric:tabular-nums}
.name{font-family:"Noto Serif SC",serif;font-weight:500;font-size:19px;color:var(--ink);
  line-height:1.35}
.tag{display:inline-block;margin-left:9px;padding:1px 8px;border-radius:20px;
  font-size:11px;font-family:"Noto Sans SC",sans-serif;background:var(--sunken);
  color:var(--muted);vertical-align:middle;font-weight:400}
.nums{display:flex;gap:10px;align-items:baseline;white-space:nowrap;
  font-family:"IBM Plex Mono",monospace;font-size:13px;
  font-variant-numeric:tabular-nums}
.n-m{color:var(--ink-2)}
.n-d{color:var(--hot);background:var(--hot-soft);padding:1px 8px;border-radius:20px}
.cites{display:none;padding:0 2px 20px 56px;margin:0;list-style:none;
  flex-direction:column;gap:13px}
.film.open .cites{display:flex}
.cite{border-left:2px solid var(--line);padding-left:14px}
.cite p{margin:0;color:var(--ink-2);white-space:pre-wrap;overflow-wrap:anywhere}
.meta{font-size:12px;color:var(--muted);font-family:"IBM Plex Mono",monospace;
  margin-top:3px}
.more{font-size:12px;color:var(--muted);padding-left:14px}
footer{margin-top:40px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12px}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media (max-width:560px){
  .wrap{padding:28px 16px 60px}
  h1{font-size:25px}
  .row{grid-template-columns:30px 1fr;gap:10px}
  .nums{grid-column:2;margin-top:4px}
  .cites{padding-left:40px}
}
"""

JS = """
(function(){
  var list=document.getElementById('list'),
      items=[].slice.call(list.children),
      q=document.getElementById('q'), cnt=document.getElementById('cnt'),
      bM=document.getElementById('by-m'), bD=document.getElementById('by-d');
  function refresh(){
    var t=q.value.trim().toLowerCase(), n=0;
    items.forEach(function(el){
      var hit=!t||el.dataset.s.indexOf(t)>-1;
      el.classList.toggle('hide',!hit); if(hit)n++;
    });
    cnt.textContent=n+' / '+items.length+' 部';
  }
  function sort(k,b){
    bM.setAttribute('aria-pressed',b===bM); bD.setAttribute('aria-pressed',b===bD);
    items.slice().sort(function(a,c){return (+c.dataset[k])-(+a.dataset[k])})
      .forEach(function(el,i){
        el.querySelector('.rank').textContent=String(i+1).padStart(2,'0');
        list.appendChild(el);
      });
  }
  q.addEventListener('input',refresh);
  bM.addEventListener('click',function(){sort('m',bM)});
  bD.addEventListener('click',function(){sort('d',bD)});
  list.addEventListener('click',function(e){
    var r=e.target.closest('.row'); if(!r)return;
    var f=r.parentNode, open=f.classList.toggle('open');
    r.setAttribute('aria-expanded',open);
  });
  refresh();
})();
"""


def render(films, units, detail_id, partial, fmt):
    ranked = sorted(films.items(), key=lambda kv: (-kv[1]["n"], -kv[1]["digg"]))
    ranked = [(k, v) for k, v in ranked if v["n"] >= 2]

    total_digg = sum(u["digg"] for u in units)
    ips = collections.Counter(u["ip"] for u in units)
    gc = collections.Counter()
    for name, f in ranked:
        g = genre_of(name)
        if g:
            gc[g] += f["n"]

    rows = []
    for i, (name, f) in enumerate(ranked, 1):
        g = genre_of(name)
        cites, shown = [], f["cites"][:10]
        for u in shown:
            tail = f' · {u["digg"]} 赞' if u["digg"] else ""
            cites.append(
                f'<li class="cite"><p>{esc(u["text"])}</p>'
                f'<div class="meta">{esc(u["nick"])} · {esc(u["ip"])}{tail}</div></li>')
        if len(f["cites"]) > len(shown):
            cites.append(
                f'<li class="more">… 另有 {len(f["cites"]) - len(shown)} 条</li>')
        blob = (name + " " + g + " " +
                " ".join(u["text"] for u in f["cites"][:40])).lower()
        tag = f'<span class="tag">{esc(g)}</span>' if g else ""
        rows.append(
            f'<li class="film" data-m="{f["n"]}" data-d="{f["digg"]}" '
            f'data-s="{esc(blob)}">'
            f'<button class="row" aria-expanded="false">'
            f'<span class="rank">{i:02d}</span>'
            f'<span class="name">{esc(name)}{tag}</span>'
            f'<span class="nums"><span class="n-m">{f["n"]} 人提</span>'
            f'<span class="n-d">{f["digg"]}</span></span></button>'
            f'<ul class="cites">{"".join(cites)}</ul></li>')

    gmax = max(gc.values()) if gc else 1
    gbars = "".join(
        f'<div class="gr"><span class="gr-t">{esc(g)}</span>'
        f'<span class="gr-b"><span class="gr-f" style="width:'
        f'{round(n / gmax * 100)}%"></span></span>'
        f'<span class="gr-n">{n}</span></div>'
        for g, n in gc.most_common())

    # partial 只说明「不是全量」，可能是还在跑，也可能是主动停了，
    # 所以用中性措辞，别写成「采集进行中」
    live = '<span class="live">部分样本</span>' if partial else ""
    note = "（评论区未采完，这是其中一段样本）" if partial else ""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    body = f"""<div class="wrap">
<header>
  <p class="eyebrow">抖音评论区 · 作品 {esc(detail_id)}</p>
  <h1>平淡却让人过目不忘的电影{live}</h1>
  <p class="lede">这条帖子问「有没有哪部电影全程平淡无高能剧情，却让你过目不忘」。
  下面是评论区自己投出来的答案——按多少人提到排序，点开任意一部能看到大家的原话。</p>
  <p class="src">统计于 {stamp} {note}</p>
</header>

<dl class="stats">
  <div class="stat"><dt>评论</dt><dd>{len(units)}</dd></div>
  <div class="stat"><dt>提到的片</dt><dd>{len(ranked)}</dd></div>
  <div class="stat"><dt>总点赞</dt><dd>{total_digg}</dd></div>
  <div class="stat"><dt>地区</dt><dd>{len(ips)}</dd></div>
</dl>

<div class="genres">{gbars}</div>

<div class="bar">
  <input type="search" id="q" placeholder="搜片名、流派，或评论里的字…" aria-label="搜索">
  <button id="by-m" aria-pressed="true">按提及人数</button>
  <button id="by-d" aria-pressed="false">按点赞</button>
  <span class="cnt" id="cnt"></span>
</div>

<ul class="list" id="list">{"".join(rows)}</ul>

<footer><p>共 {len(units)} 条评论，自动识别片名并归并同片异名，只列出被 2 人以上提到的。
点赞数为提到该片的所有评论的点赞之和。</p></footer>
</div>"""

    head = f"<title>平淡却难忘的电影</title>{FONTS}<style>{CSS}</style>"
    if fmt == "artifact":
        return f"{head}{body}<script>{JS}</script>"
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"{head}</head><body>{body}<script>{JS}</script></body></html>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file")
    ap.add_argument("--out")
    ap.add_argument("--format", choices=("standalone", "artifact"),
                    default="standalone")
    args = ap.parse_args()

    src = Path(args.json_file)
    units, detail_id, partial = load(src)
    if not units:
        print("没有数据", file=sys.stderr)
        return 1
    films, _ = analyse(units)
    out = Path(args.out) if args.out else src.parent / f"movies-{detail_id}.html"
    out.write_text(render(films, units, detail_id, partial, args.format),
                   encoding="utf-8")

    ranked = sorted(films.items(), key=lambda kv: (-kv[1]["n"], -kv[1]["digg"]))
    ranked = [(k, v) for k, v in ranked if v["n"] >= 2]
    print(f"{len(units)} 条评论 / {len(ranked)} 部片")
    for name, f in ranked[:14]:
        print(f"  {name:<16}{f['n']:>4} 人提{f['digg']:>7} 赞")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
