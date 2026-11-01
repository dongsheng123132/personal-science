#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动转正：草稿 → 实验页 → PR → （通过风险评审才）自动合并。

设计原则（对应章程与 AGENTS.md）：
  1. 限量：每个 workflow 跑一次最多 1 篇；7 天内最多 3 篇（maintenance/promote-state.json 记账）。
  2. 必须有源头：只转正能拿到 ≥2 条可点开的来源的草稿；拿不到就跳过，交给人工。
  3. 交叉评估：策展（选题）和风险（安全/物理/幻觉）各用一个独立的模型调用，
     风险模型可用 PS_RISK_MODEL 指定成和策展不同的模型。
  4. 默认不合并：只有 risk_level == low 且 verdict == approve 且 check 全绿才自动合并。
  5. 全程留痕：PR 正文 + maintenance/audit-log.md 都记下证据链。

用法：
  python collector/promote.py --dry-run          # 只挑、只生成，不提交
  python collector/promote.py --dry-run --skip-judges
  python collector/promote.py                    # 真跑（CI 里用）
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import pathlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

BASE = pathlib.Path(__file__).resolve().parent.parent
DESIGNS = BASE / "inbox" / "designs"
EXPERIMENTS = BASE / "experiments"
STATE_PATH = BASE / "maintenance" / "promote-state.json"
REJECTED_PATH = BASE / "maintenance" / "rejected.json"
REVIEWS_DIR = BASE / "reviews"
AUDIT_PATH = BASE / "maintenance" / "audit-log.md"
NOW = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")

CATS_ZH = ["物理与测量", "电子与硬件", "光与波", "生物与植物", "环境与水", "方法与思维"]
CATS_EN = {
    "物理与测量": "Physics & measurement",
    "电子与硬件": "Electronics & hardware",
    "光与波": "Light & waves",
    "生物与植物": "Biology & plants",
    "环境与水": "Environment & water",
    "方法与思维": "Method & thinking",
}

# 命中即强制人工，不交给模型判断（fail-closed）
HARD_BLOCK = ("市电", "220v", "220 v", "高压", "锂电池", "铅酸", "激光", "化学品",
              "强酸", "强碱", "水银", "汞", "放射性", "辐射源", "微生物", "菌种",
              "明火", "酒精灯", "高处作业", "屋顶", "攀爬", "强磁", "钕磁铁")

TEMPLATE_SECTIONS = ["为什么值得做", "怎么做", "AI 可以怎么帮你",
                     "算一下 / 会看到什么", "坑", "想再往前一步", "安全"]

CURATE_PROMPT = """你在给「个人科学」仓库做选题终审。下面是若干份 AI 草稿的摘要。
目标读者：想在家动手做实验的普通人；标准：好奇心第一、≤¥200、一个周末、能测出一个数、能写死验收。

从里面挑**最值得这一周上线**的 1 份，并给出：
- 分类：只能是 物理与测量 / 电子与硬件 / 光与波 / 生物与植物 / 环境与水 / 方法与思维 之一
- 中文名（去年代、去括号）、英文名
- 一句话（中文）、一句话（英文）
- 需要（中文，前 3 样东西，用、隔开）、需要（英文，用逗号隔开）
- 时间（中文）、时间（英文，如 30 min / 2 hrs / 7 days）
- 花费、难度（照抄元信息表）

只输出 JSON，不要解释：
{"pick": <草稿序号>, "score": <0-10>, "why": "<一句话>", "category_zh": "...", "name_zh": "...", "name_en": "...", "oneline_zh": "...", "oneline_en": "...", "needs_zh": "...", "needs_en": "...", "time_zh": "...", "time_en": "...", "cost": "...", "difficulty": "..."}

草稿列表：
%s
"""

RISK_PROMPT = """你是这个公开仓库的独立风险评审（只做审查，不参与写作）。作者是 AI，读者是会真的照着做的普通人。
请逐条检查下面这份实验页，找出问题：

1. 安全：有没有可能伤人（高温、高压、激光、化学品、重物、高处、电、微生物）而没写清后果和防护？
2. 物理/数值：公式、常数、量级、验收标准是否自洽？有没有明显算错？
3. 可复现：器材在国内买得到吗？步骤是否缺关键前提？验收是否真的可测？
4. 幻觉：有没有看起来像编造的型号、价格、论文、人名、年份？
5. 来源：来源是否真的支撑正文，而不是挂几个不相关的链接？

按严重度给 findings：critical（必须拦）/ warn（要人看）/ info。
verdict 规则：有 critical → reject；只有 warn → hold；无 critical 且无 warn → approve。
risk_level：critical 存在=high；有 warn=medium；都没有=low。

只输出 JSON：
{"risk_level":"low|medium|high","verdict":"approve|hold|reject","physics_ok":true/false,"safety_ok":true/false,"provenance_ok":true/false,"findings":[{"severity":"critical|warn|info","what":"...","where":"..."}],"summary":"..."}

实验页全文：
%s
"""


# ---------------------------------------------------------------- 基础工具

def run(cmd, check=True, capture=True):
    r = subprocess.run(cmd, cwd=str(BASE), shell=isinstance(cmd, str),
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.STDOUT if capture else None)
    out = (r.stdout or b"").decode("utf-8", "replace") if capture else ""
    if check and r.returncode != 0:
        raise RuntimeError("命令失败: %s\n%s" % (cmd, out[-2000:]))
    return r.returncode, out


def log(msg):
    print("[promote] " + msg, flush=True)


def llm(prompt, model_env="PS_LLM_MODEL", key_env="PS_LLM_KEY",
        base_env="PS_LLM_BASE", timeout=180):
    key = os.environ.get(key_env) or os.environ.get("PS_LLM_KEY", "")
    base = (os.environ.get(base_env) or os.environ.get("PS_LLM_BASE")
            or "https://api.deepseek.com")
    model = os.environ.get(model_env) or os.environ.get("PS_LLM_MODEL") or "deepseek-chat"
    if not key:
        raise RuntimeError("没有 PS_LLM_KEY，无法做评审")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def hard_hits(text):
    low = text.lower()
    return [w for w in HARD_BLOCK if w in low]


def json_of(text):
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("模型没返回 JSON：%r" % text[:200])
    return json.loads(m.group(0))


# ---------------------------------------------------------------- 草稿解析

def urls_in(text):
    return [u.rstrip(".,;，。；）)") for u in re.findall(r"https?://[^\s)\]>\"']+", text)]


def parse_draft(path):
    s = path.read_text(encoding="utf-8")
    m = re.search(r"^# .*$", s, re.M)
    if not m:
        return None
    body = s[m.start():]
    lines = body.split("\n")
    title = lines[0].lstrip("# ").strip()
    quote = ""
    for ln in lines[1:]:
        if ln.startswith("> "):
            quote = ln[2:].strip()
            break
    meta = {}
    for ln in lines:
        mm = re.match(r"\|\s*\*\*(需要|时间|花费|难度|验收)\*\*\s*\|\s*(.*?)\s*\|", ln)
        if mm:
            meta[mm.group(1)] = mm.group(2).strip()
    sections = {}
    cur = None
    for ln in lines:
        if ln.startswith("## "):
            cur = ln[3:].strip()
            sections[cur] = []
        elif cur:
            sections[cur].append(ln)
    sections = {k: "\n".join(v).strip() for k, v in sections.items()}
    return {"path": path, "title": title, "quote": quote, "meta": meta,
            "sections": sections, "urls": urls_in(s), "raw": s}


def clean_math(t):
    t = re.sub(r"\$\$\s*\n?(.+?)\n?\s*\$\$",
               lambda m: "```\n" + m.group(1).strip() + "\n```", t, flags=re.S)
    t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", t)
    t = re.sub(r"\\text\{([^{}]*)\}", r"\1", t)
    t = t.replace("\\cdot", "·").replace("\\Delta", "Δ").replace("\\times", "×").replace("\\quad", "  ")
    return t


def slugify(text):
    t = re.sub(r"[^a-zA-Z0-9]+", "-", str(text).lower()).strip("-")
    return t[:50]


def slug_of(title):
    return "auto-" + re.sub(r"[^a-z0-9]+", "-", urllib.parse.quote(title).lower()).strip("-")[:40]


# ---------------------------------------------------------------- 来源（不做幻觉：只用可解析的真实页面）

def wiki_resolve(term, lang):
    """用 MediaWiki opensearch 把一个词解析成真实条目 URL；解析不到返回 None。"""
    q = urllib.parse.urlencode({"action": "opensearch", "search": term,
                                "limit": 1, "format": "json",
                                "namespace": 0})
    url = "https://%s.wikipedia.org/w/api.php?%s" % (lang, q)
    ua = ("personal-science-bot/1.0 "
          "(https://github.com/dongsheng123132/personal-science)")
    for attempt in (1, 2):
        req = urllib.request.Request(url, headers={"User-Agent": ua,
                                                   "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            if len(data) > 3 and data[3]:
                return data[3][0]
            return None
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                log("wiki 解析失败(%s,%s): %s" % (lang, term, e))
            else:
                time.sleep(2)
    return None



def derive_terms(title):
    """从标题里机械地拆出可检索的概念词（不编造，只做切分）。"""
    t = re.sub(r"（[^）]*）|\([^)]*\)", "", title)
    t = t.split("：")[0].split(":")[0].strip()
    terms = [t]
    if "测" in t:
        a, b = t.split("测", 1)
        terms += [a.strip(), b.strip()]
    seen, out = set(), []
    for x in terms:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out[:4]


def wiki_langlink(url, lang="en"):
    """取一个维基条目在另一种语言里的对应页面（真实存在才返回）。"""
    try:
        title = urllib.parse.unquote(url.split("/wiki/")[-1]).replace("_", " ")
        q = urllib.parse.urlencode({"action": "query", "titles": title,
                                    "prop": "langlinks", "lllang": lang,
                                    "format": "json", "redirects": 1})
        api = "https://%s.wikipedia.org/w/api.php?%s" % (
            "zh" if "zh.wikipedia" in url else "en", q)
        ua = ("personal-science-bot/1.0 "
              "(https://github.com/dongsheng123132/personal-science)")
        req = urllib.request.Request(api, headers={"User-Agent": ua,
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        for page in data.get("query", {}).get("pages", {}).values():
            ll = page.get("langlinks")
            if ll:
                t = ll[0]["*"].replace(" ", "_")
                return "https://%s.wikipedia.org/wiki/%s" % (lang, urllib.parse.quote(t))
    except Exception as e:  # noqa: BLE001
        log("langlink 失败(%s): %s" % (url, e))
    return None


def collect_sources(draft, want=3):
    """返回 [(label, url)]。只用可解析的真实页面，不编造。"""
    out = []

    def add(label, url):
        if url and url not in [x[1] for x in out]:
            out.append((label, url))

    for u in draft["urls"]:
        if "Special:Search" in u:
            term = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("search", [""])[0]
            terms, seen = [], set()
            base = term or derive_terms(draft["title"])[0]
            for t in [base] + [x for x in derive_terms(draft["title"])
                               if x != base and len(x) >= 3]:
                if t and t not in seen:
                    seen.add(t)
                    terms.append(t)
            for t in terms:
                if len(out) >= want:
                    break
                hit = wiki_resolve(t, "zh") or wiki_resolve(t, "en")
                if hit:
                    add("维基条目：%s" % t, hit)
                    en = wiki_langlink(hit)
                    if en:
                        add("英文维基对应条目", en)
                time.sleep(0.4)
            continue
        add("原文", u)
    return out


# ---------------------------------------------------------------- 生成页面

def build_page(draft, sources, meaning=None):
    sec = draft["sections"]
    def get(name):
        return clean_math(sec.get(name, "").strip()) or "待补"
    lines = []
    lines.append("# " + draft["title"] + "\n")
    lines.append("> " + (draft["quote"] or "一句话待补") + "\n")
    lines.append("> ⚠️ 本页由 AI 草稿自动整理，并经过独立 AI 风险评审；未经人类实测，欢迎照做后回来指正。\n")
    lines.append("| | |\n|---|---|")
    for k in ["需要", "时间", "花费", "难度", "验收"]:
        lines.append("| **%s** | %s |" % (k, draft["meta"].get(k, "待补")))
    lines.append("")
    lines.append("## 为什么值得做\n\n" + get("为什么值得做") + "\n")
    if meaning:
        lines.append("## 这件事为什么重要\n\n" + meaning + "\n")
    for name in ["怎么做", "AI 可以怎么帮你", "算一下 / 会看到什么", "坑", "想再往前一步"]:
        lines.append("## %s\n\n" % name + get(name) + "\n")
    lines.append("## 安全\n\n" + get("安全") + "\n")
    lines.append("## 来源与依据\n")
    lines.append("本页内容整理自以下公开来源；每一条都可以点开核对。实验步骤与验收标准由本仓库编写，实测请自行判断。\n")
    for label, u in sources:
        lines.append("- [%s](%s)" % (label, u))
    lines.append("\n---\n\n做完把结果贴到 [RESULTS.md](../RESULTS.md)。\n")
    return "\n".join(lines)


# ---------------------------------------------------------------- README 同步

def add_readme_rows(cur, en_row, zh_row):
    p = BASE / "README.md"
    s = p.read_text(encoding="utf-8")
    # 插在对应分类表最后一行之后
    lines = s.split("\n")
    idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == "### " + cur:
            idx = i
            break
    if idx is None:
        raise RuntimeError("README.md 找不到分类 " + cur)
    j = idx + 1
    last_row = None
    while j < len(lines):
        if lines[j].startswith("|"):
            last_row = j
        elif lines[j].strip() == "" and last_row:
            break
        j += 1
    if last_row is None:
        raise RuntimeError("README.md 分类 %s 没有表格" % cur)
    lines.insert(last_row + 1, zh_row)
    p.write_text("\n".join(lines), encoding="utf-8")

    p = BASE / "README.en.md"
    s = p.read_text(encoding="utf-8")
    lines = s.split("\n")
    cur_en = CATS_EN[cur]
    idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == "### " + cur_en:
            idx = i
            break
    if idx is None:
        raise RuntimeError("README.en.md 找不到分类 " + cur_en)
    j = idx + 1
    last_row = None
    while j < len(lines):
        if lines[j].startswith("|"):
            last_row = j
        elif lines[j].strip() == "" and last_row:
            break
        j += 1
    lines.insert(last_row + 1, en_row)
    p.write_text("\n".join(lines), encoding="utf-8")


def bump_counts(old_n):
    """把 6 处实验数量从 old_n 改成 old_n+1。"""
    new_n = old_n + 1
    pats = [
        (BASE / "README.md", [("%d 个实验" % old_n, "%d 个实验" % new_n),
                              ("（%d 个）" % old_n, "（%d 个）" % new_n)]),
        (BASE / "README.en.md", [("%d experiments" % old_n, "%d experiments" % new_n),
                                 ("(%d pages)" % old_n, "(%d pages)" % new_n)]),
        (BASE / "MANIFESTO.md", [("%d 个实验" % old_n, "%d 个实验" % new_n)]),
        (BASE / "MANIFESTO.en.md", [("%d experiments" % old_n, "%d experiments" % new_n)]),
    ]
    hits = 0
    for path, pairs in pats:
        s = path.read_text(encoding="utf-8")
        for a, b in pairs:
            if a in s:
                s = s.replace(a, b)
                hits += 1
        path.write_text(s, encoding="utf-8")
    log("计数替换 %d 处：%d → %d" % (hits, old_n, new_n))


# ---------------------------------------------------------------- 限量

def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"publishes": []}
    return {"publishes": []}


def limit_ok(state):
    week_ago = (NOW - timedelta(days=7)).strftime("%Y-%m-%d")
    recent = [p for p in state.get("publishes", []) if p.get("date", "") >= week_ago]
    if len(recent) >= 3:
        log("最近 7 天已发布 %d 篇，达到上限 3，今天不转正" % len(recent))
        return False
    if any(p.get("date") == TODAY for p in recent):
        log("今天已经发布过，跳过（每天最多 1 篇）")
        return False
    return True


def save_state(state):
    state.setdefault("publishes", [])
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", "utf-8")



def push_to_main(paths, message):
    """把记录类文件直接提交到 main（和 collect 机器人写 inbox/ 一样，属于数据不是代码）。"""
    for _ in range(3):
        run(["git", "fetch", "-q", "origin", "main"], check=False)
        run(["git", "checkout", "-q", "-B", "_review", "origin/main"], check=False)
        run(["git", "add", "--"] + paths, check=False)
        rc, _ = run(["git", "commit", "-m", message], check=False)
        if rc != 0:
            return False
        rc, out = run(["git", "push", "origin", "HEAD:main"], check=False)
        if rc == 0:
            return True
        log("推 main 被拒，重试：%s" % out.strip()[-200:])
        time.sleep(3)
    return False


def write_review(slug, draft, sources, curation, risk, status, pr_url, screen=None, blocked=None):
    REVIEWS_DIR.mkdir(exist_ok=True)
    rec = {
        "slug": slug,
        "date": TODAY,
        "title": curation.get("name_zh") or draft["title"],
        "oneline": curation.get("oneline_zh") or draft["quote"],
        "category": curation.get("category_zh", ""),
        "draft": str(draft["path"].relative_to(BASE)),
        "sources": [{"label": l, "url": u} for l, u in sources],
        "curation": {"score": curation.get("score"), "why": curation.get("why", "")},
        "risk": {
            "level": risk.get("risk_level"),
            "verdict": risk.get("verdict"),
            "summary": risk.get("summary", ""),
            "physics_ok": risk.get("physics_ok"),
            "safety_ok": risk.get("safety_ok"),
            "provenance_ok": risk.get("provenance_ok"),
            "findings": risk.get("findings", []),
        },
        "status": status,
        "pr": pr_url,
        "screen": {"level": (screen or {}).get("risk_level"),
                   "verdict": (screen or {}).get("verdict")},
        "hard_block": blocked or [],
        "auto_merge": False,
    }
    rel = "reviews/%s.json" % slug
    (BASE / rel).write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", "utf-8")
    push_to_main([rel], "review: 记录 %s 的评审结果（%s）" % (slug, status))
    return rel


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-judges", action="store_true", help="不调模型（本地测试用）")
    ap.add_argument("--no-merge", action="store_true",
                    help="只开 PR 并写出决策 JSON，合并交给独立的 merge job")
    args = ap.parse_args()

    state = load_state()
    if not args.dry_run and not limit_ok(state):
        return 0

    existing_slugs = {p.stem for p in EXPERIMENTS.glob("*.md")}
    def norm_title(t):
        t = re.sub(r"\d+", "", t)                       # 去掉年代
        return re.sub(r"[^\w\u4e00-\u9fff]", "", t)     # 去掉标点空格

    existing_titles = set()
    for p in EXPERIMENTS.glob("*.md"):
        if p.name.startswith("_"):
            continue
        existing_titles.add(norm_title(p.read_text(encoding="utf-8").split("\n")[0]))

    rejected = set()
    if REJECTED_PATH.exists():
        try:
            rejected = set(json.loads(REJECTED_PATH.read_text(encoding="utf-8")).get("drafts", []))
        except json.JSONDecodeError:
            rejected = set()
    open_bodies = ""
    rc, out = run(["gh", "pr", "list", "--state", "open", "--json", "body",
                   "--jq", ".[].body"], check=False)
    if rc == 0:
        open_bodies = out
    cands = []
    for p in sorted(DESIGNS.glob("*.md"), key=lambda x: x.name):
        if p.name == "README.md":
            continue
        d = parse_draft(p)
        if not d:
            continue
        rel = str(p.relative_to(BASE))
        if rel in rejected or rel in open_bodies:
            continue
        if not all(k in d["sections"] for k in TEMPLATE_SECTIONS):
            continue
        norm = norm_title(d["title"])
        if any(t and (norm[:4] == t[:4] or norm in t or t in norm)
               for t in existing_titles):
            continue
        srcs = collect_sources(d)
        if len(srcs) < 2:
            continue
        cands.append((d, srcs))
    if not cands:
        log("没有合格候选（缺章节或来源不足 2 条）")
        return 0
    log("合格候选 %d 份" % len(cands))

    # 策展
    if args.skip_judges:
        pick = cands[0]
        curation = {"pick": 0, "score": 6, "category_zh": "物理与测量",
                    "name_zh": pick[0]["title"].split("（")[0],
                    "name_en": "Auto", "oneline_zh": pick[0]["quote"][:60],
                    "oneline_en": "Auto", "needs_zh": "待补", "needs_en": "TBD",
                    "time_zh": pick[0]["meta"].get("时间", "待补"),
                    "time_en": "TBD", "cost": pick[0]["meta"].get("花费", "待补"),
                    "difficulty": pick[0]["meta"].get("难度", "★☆☆")}
    else:
        listing = []
        for i, (d, srcs) in enumerate(cands):
            listing.append("%d. 标题：%s\n   一句话：%s\n   需要：%s\n   花费：%s\n   来源：%s" % (
                i, d["title"], d["quote"], d["meta"].get("需要", "")[:120],
                d["meta"].get("花费", ""), "；".join(u for _, u in srcs)))
        curation = json_of(llm(CURATE_PROMPT % "\n".join(listing)))
        pick = cands[int(curation.get("pick", 0))]

    draft, sources = pick
    cur_cat = curation.get("category_zh", "物理与测量")
    slug = slugify(curation.get("name_en") or "") or "experiment"
    if (EXPERIMENTS / (slug + ".md")).exists():
        slug = slug + "-2"
    log("选中：%s（策展分 %s，分类 %s）" % (draft["title"], curation.get("score"), cur_cat))

    page = build_page(draft, sources)
    blocked = hard_hits(page)
    if args.skip_judges:
        screen = {"risk_level": "low", "verdict": "approve", "findings": []}
        risk = {"risk_level": "low", "verdict": "approve", "physics_ok": True,
                "safety_ok": True, "provenance_ok": True, "findings": [],
                "summary": "skip-judges 测试模式"}
    else:
        # 第一段：便宜的预筛（Haiku）。它说不过 → 直接拦，不再花 Sonnet 的钱。
        screen = json_of(llm(RISK_PROMPT % page, model_env="PS_SCREEN_MODEL",
                             key_env="PS_RISK_KEY", base_env="PS_RISK_BASE"))
        log("预筛（%s）：%s / %s" % (
            os.environ.get("PS_SCREEN_MODEL", "haiku"),
            screen.get("risk_level"), screen.get("verdict")))
        if screen.get("verdict") in ("reject", "hold"):
            risk = screen
            risk["summary"] = "预筛已拦下：" + str(risk.get("summary", ""))
        else:
            # 第二段：终审（Sonnet），只有预筛放行才花钱
            risk = json_of(llm(RISK_PROMPT % page, model_env="PS_RISK_MODEL",
                               key_env="PS_RISK_KEY", base_env="PS_RISK_BASE"))
            log("终审（%s）：%s / %s" % (
                os.environ.get("PS_RISK_MODEL", "sonnet"),
                risk.get("risk_level"), risk.get("verdict")))
    if blocked:
        risk["risk_level"] = "high"
        risk["verdict"] = "hold"
        risk.setdefault("findings", []).insert(0, {
            "severity": "critical",
            "what": "命中硬阻断词（%s）：这类实验一律转人工，不自动合并" % "、".join(blocked),
            "where": "硬规则"})
        log("硬阻断命中：%s" % "、".join(blocked))
    log("风险评审：%s / %s" % (risk.get("risk_level"), risk.get("verdict")))
    for f in risk.get("findings", []):
        log("  - [%s] %s" % (f.get("severity"), f.get("what")))

    auto_merge = (risk.get("verdict") == "approve"
                  and risk.get("risk_level") == "low"
                  and not blocked
                  and not any(f.get("severity") == "critical"
                              for f in risk.get("findings", [])))

    if args.dry_run:
        log("dry-run：将创建 experiments/%s.md（自动合并=%s）" % (slug, auto_merge))
        log("来源：" + " | ".join(u for _, u in sources))
        print("\n" + page[:1200])
        return 0

    # 先开分支（check.py --base 要求不在 main 上）
    branch = "agent/auto-%s-%s" % (TODAY, slug)
    run(["git", "config", "user.name", "ps-bot"])
    run(["git", "config", "user.email", "ps-bot@users.noreply.github.com"])
    run(["git", "checkout", "-b", branch])

    # 写文件
    (EXPERIMENTS / (slug + ".md")).write_text(page, encoding="utf-8")
    old_n = len([p for p in EXPERIMENTS.glob("*.md") if not p.name.startswith("_")]) - 1
    zh_row = "| [%s](experiments/%s.md) | %s | %s | %s | %s | %s |" % (
        curation.get("name_zh") or draft["title"], slug,
        curation.get("oneline_zh", ""), curation.get("needs_zh", ""),
        curation.get("time_zh", ""), curation.get("cost", ""), curation.get("difficulty", ""))
    en_row = "| [%s](experiments/%s.md) | %s | %s | %s | %s | %s |" % (
        curation.get("name_en") or slug, slug,
        curation.get("oneline_en", ""), curation.get("needs_en", ""),
        curation.get("time_en", ""), curation.get("cost", ""), curation.get("difficulty", ""))
    add_readme_rows(cur_cat, en_row, zh_row)
    bump_counts(old_n)

    add_paths = ["README.md", "README.en.md", "MANIFESTO.md", "MANIFESTO.en.md",
                 str((EXPERIMENTS / (slug + ".md")).relative_to(BASE))]
    run(["git", "add", "--"] + add_paths)
    run(["git", "commit", "-m",
         "auto: 转正草稿 %s（策展 %s 分，风险 %s）" % (
             draft["title"], curation.get("score"), risk.get("risk_level"))])

    # 门禁（在分支上跑，才不会被 scope 规则拦）
    rc, out = run([sys.executable, "-X", "utf8", "maintenance/check.py",
                   "--base", "origin/main"], check=False)
    log("check.py 退出码 %d" % rc)
    if rc != 0:
        log("check.py 有 ERROR，放弃本次转正（清理现场）")
        print(out[-3000:])
        run(["git", "reset", "--hard", "origin/main"], check=False)
        run(["git", "checkout", "main"], check=False)
        run(["git", "branch", "-D", branch], check=False)
        return 1

    rc, out = run(["git", "push", "-u", "origin", branch], check=False)
    if rc != 0:
        # 同名远端分支可能是上一次（已关闭 PR）留下的，强制覆盖
        log("推送被拒，改为 force-with-lease 覆盖同名分支")
        run(["git", "push", "--force-with-lease", "-u", "origin", branch])

    body = build_pr_body(draft, sources, curation, risk, auto_merge)
    body_path = pathlib.Path("/tmp/ps-promote-pr-body.md")
    body_path.write_text(body, encoding="utf-8")
    rc, out = run(["gh", "pr", "create", "--base", "main", "--head", branch,
                   "--title", "[auto][risk:%s] 新实验：%s" % (
                       risk.get("risk_level"), curation.get("name_zh") or draft["title"]),
                   "--body-file", str(body_path)], check=False)
    if rc == 0:
        pr_url = out.strip().splitlines()[-1]
    else:
        rc2, out2 = run(["gh", "pr", "view", branch, "--json", "url",
                         "--jq", ".url"], check=False)
        if rc2 != 0:
            raise RuntimeError("创建 PR 失败：%s" % out[-1500:])
        pr_url = out2.strip()
        log("该分支已有 PR，复用：%s" % pr_url)
    log("PR: " + pr_url)
    write_review(slug, draft, sources, curation, risk,
                 "published" if auto_merge else "held", pr_url,
                 screen=screen, blocked=blocked)

    # 留痕（单独一个提交推到同一分支）
    if not AUDIT_PATH.exists():
        AUDIT_PATH.write_text("# 自动转正审计日志\n\n"
                              "| 日期 | 标题 | slug | 策展分 | 风险 | PR |\n"
                              "|---|---|---|---|---|---|\n", encoding="utf-8")
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write("| %s | %s | %s | %s | %s | %s |\n" % (
            TODAY, draft["title"], slug, curation.get("score"),
            risk.get("risk_level"), pr_url))
    run(["git", "add", "--", "maintenance/audit-log.md"])
    run(["git", "commit", "-m", "audit: 记录自动转正 " + slug])
    run(["git", "push"], check=False)

    decision = {"slug": slug, "pr": pr_url, "auto_merge": bool(auto_merge),
                "risk_level": risk.get("risk_level"), "verdict": risk.get("verdict"),
                "hard_block": blocked, "date": TODAY, "model_screen": os.environ.get("PS_SCREEN_MODEL"),
                "model_final": os.environ.get("PS_RISK_MODEL")}
    pathlib.Path("/tmp/promote-decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=1), "utf-8")
    if auto_merge and not args.no_merge:
        merged = wait_and_merge(pr_url)
        if merged:
            state["publishes"].append({"date": TODAY, "slug": slug, "pr": pr_url})
            save_state(state)
    else:
        log("不自动合并（verdict=%s, risk=%s），PR 保留给人工" % (
            risk.get("verdict"), risk.get("risk_level")))
    return 0


def build_pr_body(draft, sources, curation, risk, auto_merge):
    srcs = "\n".join("- %s：%s" % (l, u) for l, u in sources)
    findings = "\n".join("- [%s] %s（%s）" % (f.get("severity"), f.get("what"), f.get("where", ""))
                         for f in risk.get("findings", [])) or "（无）"
    return """## 这是什么

由 `collector/promote.py` 自动把一份 AI 草稿转成实验页。**AI 只提 PR；是否合并由风险评审决定。**

## 来源与依据（审计用，必须可点开核对）

%s

- 草稿文件：`%s`

## 策展（第一个模型）

- 分类：%s
- 分数：%s / 10
- 理由：%s

## 独立风险评审（第二个模型：`%s`）

- risk_level：**%s**
- verdict：**%s**
- physics_ok=%s · safety_ok=%s · provenance_ok=%s
- 结论：%s

### findings

%s

## 自动合并

%s

---
本 PR 由机器人创建。人类可以随时关闭或用 `hold` 标签压住。
""" % (srcs, draft["path"].relative_to(BASE), curation.get("category_zh"),
       curation.get("score"), curation.get("why", ""),
       os.environ.get("PS_RISK_MODEL") or os.environ.get("PS_LLM_MODEL") or "default",
       risk.get("risk_level"), risk.get("verdict"),
       risk.get("physics_ok"), risk.get("safety_ok"), risk.get("provenance_ok"),
       risk.get("summary", ""), findings,
       "满足全部条件（risk=low, verdict=approve, check 全绿），等待 CI 通过后自动 squash 合并。"
       if auto_merge else "不满足自动合并条件，等待人工处理。")


def wait_and_merge(pr_url, timeout_min=20):
    """等 CI 跑完，绿了才合并。"""
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        time.sleep(30)
        rc, out = run(["gh", "pr", "checks", pr_url, "--json", "state"],
                      check=False)
        try:
            states = [c.get("state") for c in json.loads(out or "[]")]
        except json.JSONDecodeError:
            states = []
        if states and all(s == "SUCCESS" for s in states):
            rc, out = run(["gh", "pr", "merge", pr_url, "--squash",
                           "--delete-branch"], check=False)
            log("合并：%s" % out.strip()[-300:])
            return rc == 0
        if any(s in ("FAILURE", "CANCELLED") for s in states):
            log("CI 失败，不合并")
            return False
    log("等 CI 超时，不合并")
    return False


if __name__ == "__main__":
    sys.exit(main())
