#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""personal-science 采集器 v0.1

定期从公开源扫"个人能做的科学项目"，去重、打分、写候选池和每日看板。
纯标准库，不需要数据库，不需要服务器（GitHub Actions 跑就行）。

用法:
    python collector/collect.py                 # 采集 + 写 feed/inbox
    python collector/collect.py --no-llm        # 关掉 AI 推荐理由
    python collector/collect.py --limit 20      # 只保留前 20 条

环境变量（都可选）:
    GITHUB_TOKEN   GitHub 搜索用，没 token 也能跑（限速低）
    PS_LLM_BASE    如 https://api.deepseek.com
    PS_LLM_KEY     有 key 才写"推荐理由"
    PS_LLM_MODEL   默认 deepseek-chat
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE / "collector" / "sources.json"
SEEN_PATH = BASE / "collector" / "seen.json"
FEED_DIR = BASE / "feed"
INBOX_DIR = BASE / "inbox"

UA = "personal-science-collector/0.1"
NOW = datetime.now(timezone.utc)

# 相关性闸门：一条内容必须同时命中"科学物件"和"个人动手"才算候选。
# 只有前者 = 新闻/论文；只有后者 = 普通 DIY 教程。
OBJECTS = [
    "spectrometer", "microscope", "telescope", "geiger", "radiation", "air quality",
    "water quality", "soil", "plant", "germination", "fermentation", "chemistry",
    "physics", "biology", "astronomy", "ecology", "sensor", "calibrat",
    "temperature", "humidity", "pressure", "acoustic", "spectrum", "optics",
    "magnet", "radio", "weather", "ph ", "conductivity", "laser", "camera",
    "imaging", "measurement", "lab notebook",
    "实验", "测量", "传感器",
]
PERSONAL = [
    "build", "built", "made", "diy", "home", "backyard", "cheap", "under $",
    "self", "arduino", "raspberry pi", "3d print", "自己", "自制", "在家",
]
NEGATIVE = [
    "hiring", "giveaway", "airdrop", "coupon", "casino", "betting", "sponsored",
    "launch hn", "show hn", "ask hn", "yc f", "yc s", "招聘", "融资", "webinar",
]
# 能用今天的工具（AI / 单片机 / 手机）重做的加分
MODERN_TOOLS = [
    "esp32", "arduino", "raspberry", "smartphone", "手机", "传感器", "sensor",
    "laser", "激光", "camera", "相机", "开源", "open source", "3d print",
    "python", "imagej", "人工智能", "大模型", "machine learning",
]


# ---------------------------------------------------------------- 工具


def log(msg):
    print(msg, file=sys.stderr)


def fetch(url, headers=None, timeout=25, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.2 * (i + 1))
    log(f"  ! 取不到 {url[:90]} ({type(last).__name__}: {last})")
    return None


def parse_date(raw):
    if not raw:
        return None
    raw = raw.strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def strip_tags(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def norm_url(url):
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url.strip())
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query) if not k.startswith("utm_")]
    return urllib.parse.urlunsplit((
        parsed.scheme.lower() or "https",
        parsed.netloc.lower(),
        parsed.path.rstrip("/") or "/",
        urllib.parse.urlencode(query),
        "",
    ))


def make_item(source, title, url, published, summary="", meta=None, targeted=False):
    title = strip_tags(title)
    summary = strip_tags(summary)[:400]
    clean_url = norm_url(url)
    if not title or not clean_url:
        return None
    # RSS 是 RFC822（Fri, 08 Nov 2024 …），API 是 ISO，统一成 YYYY-MM-DD
    parsed = parse_date(published)
    published_iso = parsed.strftime("%Y-%m-%d") if parsed else (published or "")[:10]
    return {
        "id": hashlib.sha1(clean_url.encode("utf-8")).hexdigest()[:12],
        "source": source,
        "title": title,
        "url": clean_url,
        "published": published_iso,
        "summary": summary,
        "meta": meta or {},
        "targeted": targeted,
        "score": 0,
        "why": "",
    }


# ---------------------------------------------------------------- 各来源


def collect_github(cfg):
    items, token = [], os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    per = int(cfg.get("per_query", 8))
    for query in cfg.get("queries", []):
        url = ("https://api.github.com/search/repositories?q=" + urllib.parse.quote(query)
               + f"&sort=stars&order=desc&per_page={per}")
        raw = fetch(url, headers)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for repo in payload.get("items", []):
            item = make_item(
                "github", repo.get("full_name", ""), repo.get("html_url", ""),
                repo.get("pushed_at", ""), repo.get("description") or "",
                {"stars": repo.get("stargazers_count", 0), "topics": repo.get("topics", [])},
            )
            if item:
                items.append(item)
    return items


def collect_hn(cfg):
    items = []
    since = int((NOW - timedelta(days=int(cfg.get("days", 60)))).timestamp())
    for query in cfg.get("queries", []):
        url = ("https://hn.algolia.com/api/v1/search?query=" + urllib.parse.quote(query)
               + "&tags=story&hitsPerPage=12&numericFilters=created_at_i>" + str(since))
        raw = fetch(url)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for hit in payload.get("hits", []):
            story = hit.get("story_text") or ""
            blob = (hit.get("title", "") + " " + story).lower()
            tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
            if tokens and not all(t in blob for t in tokens):
                continue  # Algolia 是"任一命中"排序，这里强制要求全词命中
            link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            item = make_item(
                "hn", hit.get("title", ""), link, hit.get("created_at", ""),
                hit.get("story_text") or "",
                {"points": hit.get("points", 0), "comments": hit.get("num_comments", 0)},
            )
            if item:
                items.append(item)
    return items


def sanitize_xml(raw):
    """很多 RSS 的 HTML 里 & 没转义、命名空间没声明。这里用宽松正则解析，不跟 XML 较劲。"""
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    return raw


def _grab(block, tag):
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S | re.I)
    if not match:
        return ""
    text = match.group(1)
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.S)
    return strip_tags(text)


def parse_feed(raw):
    """宽松解析 RSS item / Atom entry，坏 XML 也能出东西。"""
    blocks = re.findall(r"<item[\s>].*?</item>", raw, re.S | re.I)
    if not blocks:
        blocks = re.findall(r"<entry[\s>].*?</entry>", raw, re.S | re.I)
    parsed = []
    for block in blocks:
        link = _grab(block, "link")
        if not link:
            href = re.search(r'<link[^>]+href="([^"]+)"', block, re.I)
            if href:
                link = href.group(1)
        title = _grab(block, "title")
        summary = (_grab(block, "description") or _grab(block, "summary")
                   or _grab(block, "content:encoded") or _grab(block, "content"))
        date = (_grab(block, "pubDate") or _grab(block, "published") or _grab(block, "updated"))
        parsed.append({"title": title, "link": link, "summary": summary, "date": date})
    return parsed


def collect_wordpress(cfg):
    """WordPress 站点的搜索接口。比 RSS 精准得多：直接按"光谱仪""盖革计数器"搜。"""
    items = []
    per = int(cfg.get("per_query", 5))
    for site in cfg.get("sites", []):
        host = urllib.parse.urlsplit(site).netloc.replace("www.", "").split(".")[0]
        for query in cfg.get("queries", []):
            url = (f"{site.rstrip('/')}/wp-json/wp/v2/posts?search={urllib.parse.quote(query)}"
                   f"&per_page={per}&_fields=title,link,date,excerpt")
            raw = fetch(url, {"Accept": "application/json"})
            if not raw:
                continue
            try:
                posts = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(posts, list):
                continue
            for post in posts:
                title = re.sub(r"<[^>]+>", "", post.get("title", {}).get("rendered", ""))
                excerpt = re.sub(r"<[^>]+>", "", post.get("excerpt", {}).get("rendered", ""))
                item = make_item(host, title, post.get("link", ""), post.get("date", ""),
                                 excerpt, {"query": query}, targeted=True)
                if item:
                    items.append(item)
        log(f"  · {host}: 累计 {len(items)} 条")
    return items


def collect_feeds(cfg):
    """通用 RSS/Atom 采集。Hackster、Hackaday、Arduino、Instructables 都是这个形状。"""
    items = []
    for feed in cfg.get("feeds", []):
        if not feed.get("enabled", True):
            continue
        raw = fetch(feed.get("url", ""))
        if not raw:
            continue
        entries = parse_feed(raw)
        count = 0
        for entry in entries:
            item = make_item(
                feed["name"], entry["title"], entry["link"], entry["date"], entry["summary"],
            )
            if item:
                items.append(item)
                count += 1
        log(f"  · {feed['name']}: {count} 条")
    return items


def collect_arxiv(cfg):
    items = []
    for query in cfg.get("queries", []):
        url = ("http://export.arxiv.org/api/query?search_query="
               + urllib.parse.quote(f'all:"{query}"')
               + f"&sortBy=submittedDate&sortOrder=descending&max_results={int(cfg.get('max_results', 8))}")
        raw = fetch(url)
        if not raw:
            continue
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            continue
        for entry in root.iter():
            if entry.tag.split("}")[-1] != "entry":
                continue
            fields = {}
            for child in entry:
                tag = child.tag.split("}")[-1]
                if tag in ("title", "summary", "published", "id"):
                    fields[tag] = (child.text or "").strip()
            item = make_item("arxiv", fields.get("title", ""), fields.get("id", ""),
                             fields.get("published", ""), fields.get("summary", ""))
            if item:
                items.append(item)
    return items


def collect_classics(cfg):
    """本地种子库：经典实验。年代不限，越老越值钱——因为它们都还能重做。"""
    path = BASE / cfg.get("path", "collector/classics.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text("utf-8"))
    items = []
    for entry in data.get("items", []):
        title = entry.get("zh") or entry.get("en") or entry["id"]
        if entry.get("era"):
            title = f"{title}（{entry['era']}）"
        summary = "；".join(filter(None, [
            entry.get("what"),
            f"重做方式：{entry['redo']}" if entry.get("redo") else "",
            f"为什么值得：{entry['why']}" if entry.get("why") else "",
            f"难度：{entry['level']}" if entry.get("level") else "",
        ]))
        url = ("https://zh.wikipedia.org/wiki/Special:Search?search="
               + urllib.parse.quote(entry.get("zh") or entry.get("en") or entry["id"]))
        item = make_item("classic", title, url, "", summary,
                         {"era": entry.get("era", ""), "level": entry.get("level", ""),
                          "tools": entry.get("tools", [])}, targeted=True)
        if item:
            item["timeless"] = True
            items.append(item)
    log(f"  · classics: {len(items)} 条")
    return items


def collect_wikipedia(cfg):
    """维基百科搜索：经典实验、思想实验、科学史条目。天然'不限年代'。"""
    items = []
    for site in cfg.get("sites", ["zh.wikipedia.org"]):
        for query in cfg.get("queries", []):
            url = ("https://" + site + "/w/api.php?action=query&format=json&generator=search"
                   f"&gsrsearch={urllib.parse.quote(query)}&gsrlimit={int(cfg.get('limit', 8))}"
                   "&prop=extracts|info&exintro=1&explaintext=1&inprop=url")
            raw = fetch(url, {"Accept": "application/json"})
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            pages = (payload.get("query") or {}).get("pages") or {}
            for page in pages.values():
                item = make_item("wikipedia", page.get("title", ""), page.get("fullurl", ""),
                                 "", (page.get("extract") or "")[:400], {"site": site}, targeted=True)
                if item:
                    item["timeless"] = True
                    items.append(item)
        log(f"  · wikipedia/{site}: 累计 {len(items)} 条")
    return items


# ---------------------------------------------------------------- 打分


def days_old(published):
    dt = parse_date(published)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (NOW - dt).days)


def score(item):
    blob = (item["title"] + " " + item["summary"]).lower()
    base = {"classic": 66, "wikipedia": 52, "hackaday": 58, "hackster": 55,
            "makezine": 50, "instructables": 55, "hn": 50, "github": 45,
            "arxiv": 38}.get(item["source"], 45)
    objs = [kw for kw in OBJECTS if kw in blob]
    pers = [kw for kw in PERSONAL if kw in blob]
    modern = [kw for kw in MODERN_TOOLS if kw in blob]
    base += min(20, len(objs) * 10)
    base += min(10, len(pers) * 4)
    base += min(12, len(modern) * 3)
    if item.get("targeted"):
        base += 8
    if item.get("timeless"):
        base += 6  # 经典实验没有"过期"这回事
    base -= min(40, sum(15 for kw in NEGATIVE if kw in blob))

    # 只有"新闻型"来源才看新鲜度；经典/维基条目不按年代扣分
    if not item.get("timeless"):
        age = days_old(item["published"])
        if age is not None:
            base += 8 if age <= 7 else 4 if age <= 30 else 0 if age <= 90 else -10

    stars = item["meta"].get("stars", 0)
    if stars:
        base += min(10, int((stars ** 0.5) / 3))
    points = item["meta"].get("points", 0)
    if points:
        base += min(8, points // 25)

    item["score"] = max(0, min(100, base))
    item["obj_hits"] = objs[:3]
    item["per_hits"] = pers[:3]
    item["modern_hits"] = modern[:3]
    item["hits"] = (objs + pers + modern)[:3]
    item["title_signal"] = bool(
        any(kw in item["title"].lower() for kw in OBJECTS)
        or any(kw in item["title"].lower() for kw in PERSONAL)
    )
    return item


def heuristic_why(item):
    bits = []
    if item["hits"]:
        bits.append("命中 " + "、".join(item["hits"]))
    if item["meta"].get("stars"):
        bits.append(f"{item['meta']['stars']} 星")
    if item["meta"].get("points"):
        bits.append(f"{item['meta']['points']} 点")
    if item["published"]:
        bits.append(item["published"])
    return "，".join(bits) or f"来自 {item['source']}"


def llm_reason(item):
    base = (os.environ.get("PS_LLM_BASE") or "https://api.deepseek.com").rstrip("/")
    key = os.environ.get("PS_LLM_KEY", "")
    model = os.environ.get("PS_LLM_MODEL", "deepseek-chat")
    if not (base and key):
        return None
    prompt = (
        "下面是候选内容。用一句中文（不超过 40 字）说明：普通人能不能在家复现、或者它为什么值得进"
        "'个人科学'清单。只输出这一句，不要前缀。\n\n"
        f"标题：{item['title']}\n来源：{item['source']}\n摘要：{item['summary'][:300]}"
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 120,
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            base + "/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"].strip()
        return text.splitlines()[0][:80]
    except Exception as exc:  # noqa: BLE001
        log(f"  ! LLM 失败: {type(exc).__name__}: {exc}")
        return None


# ---------------------------------------------------------------- 输出


def load_seen():
    if SEEN_PATH.exists():
        try:
            return json.loads(SEEN_PATH.read_text("utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_seen(seen):
    cutoff = (NOW - timedelta(days=120)).strftime("%Y-%m-%d")
    pruned = {k: v for k, v in seen.items() if v >= cutoff}
    SEEN_PATH.write_text(json.dumps(pruned, ensure_ascii=False, indent=1) + "\n", "utf-8")


def write_feed(items):
    FEED_DIR.mkdir(exist_ok=True)
    payload = {
        "generated_at": NOW.isoformat(timespec="seconds"),
        "date": NOW.strftime("%Y-%m-%d"),
        "count": len(items),
        "items": items,
    }
    blob = json.dumps(payload, ensure_ascii=False, indent=1)
    (FEED_DIR / "latest.json").write_text(blob + "\n", "utf-8")
    (FEED_DIR / "latest.js").write_text(
        "// 自动生成，勿手改\nwindow.PS_FEED = " + blob + ";\n", "utf-8")


def write_raw(items):
    INBOX_DIR.mkdir(exist_ok=True)
    payload = {
        "generated_at": NOW.isoformat(timespec="seconds"),
        "date": NOW.strftime("%Y-%m-%d"),
        "count": len(items),
        "items": items,
    }
    (INBOX_DIR / "raw.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", "utf-8")


def update_pool(items):
    """14 天滚动池。每天的 raw 只有当天新增，AI 看到的太少；池子才是它的输入。"""
    pool_path = INBOX_DIR / "pool.json"
    pool = []
    if pool_path.exists():
        try:
            pool = json.loads(pool_path.read_text("utf-8")).get("items", [])
        except json.JSONDecodeError:
            pool = []
    fresh = {i["id"] for i in items}
    merged = items + [p for p in pool if p.get("id") not in fresh]
    cutoff = (NOW - timedelta(days=30)).strftime("%Y-%m-%d")
    merged = [m for m in merged
              if m.get("timeless") or not m.get("published") or m["published"] >= cutoff]
    merged.sort(key=lambda x: (x.get("score", 0), x.get("published", "")), reverse=True)
    merged = merged[:150]
    pool_path.write_text(json.dumps({
        "updated_at": NOW.isoformat(timespec="seconds"),
        "count": len(merged),
        "items": merged,
    }, ensure_ascii=False, indent=1) + "\n", "utf-8")


def write_prefilter(items):
    INBOX_DIR.mkdir(exist_ok=True)
    lines = [
        f"# 机器初筛 · {NOW.strftime('%Y-%m-%d')}",
        "",
        f"关键词命中 **{len(items)}** 条。这只是筛子，不是判断——**真正挑哪条要人（或 AI）看**。",
        "",
        "完整原始池在 [raw.json](raw.json)。挑出来的写进 `inbox/candidates.md`，",
        "再照着 [实验模板](../experiments/_template.md) 写成页面，提 PR 进清单。",
        "",
    ]
    for item in items:
        lines.append(f"- **{item['title']}** — {item['score']} 分 · `{item['source']}` · "
                     f"{item['published'] or '无日期'} · [打开]({item['url']})")
    (INBOX_DIR / "prefilter.md").write_text("\n".join(lines) + "\n", "utf-8")


# ---------------------------------------------------------------- 主流程


def main():
    parser = argparse.ArgumentParser(description="personal-science 采集器")
    parser.add_argument("--no-llm", action="store_true", help="不给 AI 写推荐理由")
    parser.add_argument("--limit", type=int, default=30, help="最多保留多少条")
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text("utf-8"))
    seen = load_seen()

    collectors = {
        "classics": collect_classics,
        "wikipedia": collect_wikipedia,
        "wordpress": collect_wordpress,
        "feeds": collect_feeds,
        "github": collect_github,
        "hn": collect_hn,
        "arxiv": collect_arxiv,
    }

    raw_items = []
    for name, fn in collectors.items():
        cfg = config.get(name, {})
        if not cfg.get("enabled", False):
            continue
        log(f"· 扫 {name} …")
        try:
            got = fn(cfg)
        except Exception as exc:  # noqa: BLE001
            log(f"  ! {name} 出错: {type(exc).__name__}: {exc}")
            got = []
        log(f"  {len(got)} 条")
        raw_items.extend(got)

    # 去重：URL id + 标题指纹。注意这里**不排除"见过"的**——
    # 见过的东西也要进滚动池，否则某天没新内容，AI 就没东西可筛。
    unique, titles = [], set()
    for item in raw_items:
        fingerprint = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", item["title"].lower())[:48]
        if item["id"] in {u["id"] for u in unique}:
            continue
        if fingerprint and fingerprint in titles:
            continue
        titles.add(fingerprint)
        unique.append(item)

    for item in unique:
        score(item)

    unique.sort(key=lambda x: x["score"], reverse=True)
    update_pool(unique)  # 池子收本轮抓到的全部内容

    # 今天新增 = 没见过的
    fresh = [i for i in unique if i["id"] not in seen]
    wide = fresh[: max(120, args.limit * 4)]   # 宽网：全部留给人工/AI 复核
    write_raw(wide)
    log(f"· 本轮抓到 {len(unique)} 条去重后内容，其中 {len(fresh)} 条是新的")

    # 关键词闸门只对"撒网型"来源生效；定向搜索（WordPress 查询）自带主题，不再筛
    kept = [i for i in wide
            if i.get("targeted")
            or (i.get("obj_hits") and i.get("per_hits") and i.get("title_signal"))]
    dropped = len(wide) - len(kept)
    if dropped:
        log(f"· 关键词粗筛丢掉 {dropped} 条")
    kept = kept[: args.limit]

    for item in kept:
        item["why"] = ((llm_reason(item) if not args.no_llm else None) or heuristic_why(item))

    write_feed(kept)
    write_prefilter(kept)

    today = NOW.strftime("%Y-%m-%d")
    for item in wide:
        seen[item["id"]] = today
    save_seen(seen)

    log(f"\n粗筛入选 {len(kept)} 条，原始池 {len(wide)} 条")


if __name__ == "__main__":
    main()
