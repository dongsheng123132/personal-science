#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机械体检：只读，不改任何文件，不写基线。

用法：
  python -X utf8 maintenance/check.py                     全量检查
  python -X utf8 maintenance/check.py --base origin/main  额外做"改动范围"检查
  python -X utf8 maintenance/check.py --json              机器可读输出（可与 --base 同用）

退出码：0 = 没有 ERROR；1 = 有 ERROR；2 = 用法错误或环境问题。
级别：ERROR（导致退出码 1）、WARN、REVIEW（需要 Claude 或主人审）、INFO。

文件集合只从 git 取（git ls-files ∪ 已暂存的新文件 ∪ 未跟踪且未被忽略的文件），
绝不遍历文件系统；.tmp/ 下的路径只按路径报错，内容一律不读。
只用标准库，兼容 Python 3.9+。
"""
import argparse
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "maintenance/check_baseline.json"
TEMPLATE = "experiments/_template.md"
LEVELS = ("ERROR", "WARN", "REVIEW", "INFO")


class EnvError(Exception):
    """环境问题或用法问题，退出码 2。"""


class Report:
    def __init__(self):
        self.items = {lv: [] for lv in LEVELS}

    def add(self, level, rule, path, line, message):
        self.items[level].append(
            {"rule": rule, "path": path, "line": line, "message": message})


# ---------------------------------------------------------------- git / 文件

def git(args, ok_codes=(0,)):
    try:
        r = subprocess.run(["git"] + list(args), cwd=str(ROOT),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        raise EnvError("运行 git 失败：%s" % e)
    if r.returncode not in ok_codes:
        err = r.stderr.decode("utf-8", "replace").strip()
        raise EnvError("git %s 失败（退出码 %d）：%s"
                       % (" ".join(args), r.returncode, err))
    return r


def split_z(raw):
    return [p for p in raw.decode("utf-8", "replace").split("\0") if p]


def split_lines(text):
    """按 \\n 切行（行号与编辑器一致），去掉行尾 \\r。"""
    return [ln[:-1] if ln.endswith("\r") else ln for ln in text.split("\n")]


class Context:
    def __init__(self):
        r = git(["rev-parse", "--show-toplevel"], ok_codes=(0, 128))
        if r.returncode != 0:
            raise EnvError("不在 git 仓库里：%s" % ROOT)
        top = r.stdout.decode("utf-8", "replace").strip()
        try:
            same = os.path.samefile(top, str(ROOT))
        except OSError:
            same = False
        if not same:
            raise EnvError("check.py 必须放在仓库根下的 maintenance/（git 根是 %s）"
                           % top)
        self.tracked = split_z(git(["ls-files", "-z"]).stdout)
        staged_new = split_z(git(["diff", "--cached", "--name-only",
                                  "--diff-filter=ACMR", "-z"]).stdout)
        untracked = split_z(git(["ls-files", "--others", "--exclude-standard",
                                 "-z"]).stdout)
        self.tracked_set = set(self.tracked)
        self.files = sorted(self.tracked_set | set(staged_new) | set(untracked))
        self.files_set = set(self.files)
        # .tmp/ 不属于本项目：只按路径报 secrets ERROR，内容一律不读
        self.existing = [p for p in self.files
                         if not p.startswith(".tmp/") and (ROOT / p).is_file()]
        self.existing_set = set(self.existing)
        dirs = {""}
        for p in self.files:
            parts = p.split("/")[:-1]
            for k in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:k]))
        self.dirs_set = dirs
        # 不区分大小写的对照表：小写路径 -> git 里的真实写法
        self.lower_map = {}
        for p in sorted(dirs | self.files_set):
            self.lower_map.setdefault(p.lower(), p)
        self._cache = {}
        # 因为太大或是二进制而没扫密钥的文件（--base 时对改动范围内的报 WARN）
        self.secret_skipped = set()

    def read_bytes(self, rel):
        if rel not in self._cache:
            try:
                self._cache[rel] = (ROOT / rel).read_bytes()
            except OSError:
                self._cache[rel] = None
        return self._cache[rel]

    def read_text(self, rel):
        data = self.read_bytes(rel)
        if data is None:
            return None
        return data.decode("utf-8", "replace").lstrip("\ufeff")


def first_nonempty(lines):
    for ln in lines:
        if ln.strip():
            return ln
    return ""


HTML_BLOCK_COMMENT_RE = re.compile(r"^ {0,3}<!--")


def strip_inline_comments(ln):
    """删掉一行里的 HTML 注释。返回 (剩下的文本, 是否停在没闭合的注释里)。"""
    parts = []
    pos = 0
    while True:
        start = ln.find("<!--", pos)
        if start == -1:
            parts.append(ln[pos:])
            return "".join(parts), False
        parts.append(ln[pos:start])
        end = ln.find("-->", start + 4)
        if end == -1:
            return "".join(parts), True
        pos = end + 3


def visible_lines(text, keep_fences=False):
    """按 split_lines 切行，但把 HTML 注释和围栏代码块换成空行，行号不变。

    行首（最多 3 个空格）就是 <!-- 的：从这一行到含 --> 的那一行整行清空（HTML 块）。
    行中间的注释只删注释本身；跨行的，中间行清空，闭合那一行 --> 之前的部分换成
    一个空格（剩下的文本不在行首，不会被当成标题或表格行）。
    围栏沿用 fence_step 的规则；围栏里的 <!-- 不算注释，注释里的 ``` 不算围栏。
    keep_fences=True：围栏代码块原样保留（GitHub 上看得见），只去掉注释。
    """
    out = []
    fence = None
    comment = None          # None / "block" / "inline"
    for ln in split_lines(text):
        if comment is not None:
            end = ln.find("-->")
            if end == -1:
                out.append("")
                continue
            if comment == "block":
                comment = None
                out.append("")
                continue
            vis, still_open = strip_inline_comments(ln[end + 3:])
            comment = "inline" if still_open else None
            out.append(" " + vis)
            continue
        if fence is not None:
            fence, _ = fence_step(ln, fence)
            out.append(ln if keep_fences else "")
            continue
        fence, is_fence_line = fence_step(ln, None)
        if is_fence_line:
            out.append(ln if keep_fences else "")
            continue
        m = HTML_BLOCK_COMMENT_RE.match(ln)
        if m:
            if ln.find("-->", m.end()) == -1:
                comment = "block"
            out.append("")
            continue
        vis, still_open = strip_inline_comments(ln)
        if still_open:
            comment = "inline"
        out.append(vis)
    return out


# ---------------------------------------------------------------- 1. secrets

SECRET_EXTS = {".pem", ".p12", ".pfx", ".key", ".keystore", ".jks"}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bLTAI[0-9A-Za-z]{12,}\b"),
]
MAX_SCAN = 2 * 1024 * 1024


def has_secret(ln):
    return any(rx.search(ln) for rx in SECRET_PATTERNS)


def secret_path_reason(path):
    name = path.rsplit("/", 1)[-1]
    low = name.lower()
    ext = "." + low.rsplit(".", 1)[-1] if "." in low else ""
    if path.startswith(".tmp/"):
        return ".tmp/ 下的文件不能进仓库"
    if name == ".env" or name.startswith(".env."):
        return "环境变量文件不能进仓库"
    if ext in SECRET_EXTS:
        return "私钥/证书文件不能进仓库"
    if "apiclient_key" in low or "apiv3" in low:
        return "疑似支付密钥文件，不能进仓库"
    return None


def rule_secrets(ctx, rep):
    flagged = set()
    for p in ctx.files:
        reason = secret_path_reason(p)
        if reason:
            flagged.add(p)
            rep.add("ERROR", "secrets", p, None, reason)

    for p in ctx.existing:
        if p in flagged:
            continue
        try:
            if (ROOT / p).stat().st_size > MAX_SCAN:
                ctx.secret_skipped.add(p)
                continue
        except OSError:
            continue
        data = ctx.read_bytes(p)
        if data is None:
            continue
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            # UTF-16（Windows 上 PowerShell 重定向会写成这样）：解码后照扫
            text = data.decode("utf-16", "replace")
        elif b"\0" in data[:8192]:
            ctx.secret_skipped.add(p)
            continue
        else:
            text = data.decode("utf-8", "replace")
        for i, ln in enumerate(split_lines(text), 1):
            if has_secret(ln):
                # 绝不打印匹配到的值
                rep.add("ERROR", "secrets", p, i, "疑似私钥/密钥（值已隐藏）")

    gi = ROOT / ".gitignore"
    if not gi.is_file():
        rep.add("ERROR", "secrets", ".gitignore", None,
                "根目录缺 .gitignore（必须有一行 .tmp/）")
    else:
        try:
            text = gi.read_bytes().decode("utf-8", "replace").lstrip("\ufeff")
        except OSError:
            text = ""
        gi_lines = split_lines(text)
        if not any(ln.rstrip() == ".tmp/" for ln in gi_lines):
            rep.add("ERROR", "secrets", ".gitignore", None,
                    ".gitignore 里没有恰为 .tmp/ 的一行")
        for i, ln in enumerate(gi_lines, 1):
            if ln.startswith("!") and ".tmp" in ln:
                rep.add("ERROR", "secrets", ".gitignore", i,
                        ".gitignore 不能取消忽略 .tmp/")
    if ".gitignore" not in ctx.tracked_set:
        rep.add("WARN", "secrets", ".gitignore", None, ".gitignore 还没提交")


# ---------------------------------------------------------------- 2. json

JS_FEED = "feed/latest.js"
JS_PREFIX = re.compile(r"^window\.PS_FEED\s*=\s*")


def rule_json(ctx, rep):
    for p in ctx.existing:
        if not p.endswith(".json"):
            continue
        data = ctx.read_bytes(p)
        if data is None:
            continue
        if data.startswith(b"\xef\xbb\xbf"):
            rep.add("ERROR", "json", p, None,
                    "文件开头有 UTF-8 BOM，去掉（Windows 记事本 / PowerShell 会加）")
            data = data[3:]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            rep.add("ERROR", "json", p, None, "不是合法 UTF-8")
            continue
        try:
            json.loads(text)
        except ValueError as e:
            rep.add("ERROR", "json", p, getattr(e, "lineno", None),
                    "JSON 解析失败：%s" % getattr(e, "msg", e))

    if JS_FEED in ctx.existing_set:
        data = ctx.read_bytes(JS_FEED)
        try:
            text = data.decode("utf-8").lstrip("\ufeff")
        except UnicodeDecodeError:
            rep.add("ERROR", "json", JS_FEED, None, "不是合法 UTF-8")
            return
        lines = text.split("\n")
        idx = 0
        # 跳过开头的空行和 // 注释行（collect.py 会写一行 "// 自动生成，勿手改"）
        while idx < len(lines) and (not lines[idx].strip()
                                    or lines[idx].lstrip().startswith("//")):
            idx += 1
        body = "\n".join(lines[idx:])
        m = JS_PREFIX.match(body)
        if not m:
            rep.add("ERROR", "json", JS_FEED, idx + 1 if idx < len(lines) else None,
                    "开头不是 window.PS_FEED = ")
            return
        rest = body[m.end():].rstrip().rstrip(";")
        try:
            json.loads(rest)
        except ValueError as e:
            ln = getattr(e, "lineno", None)
            rep.add("ERROR", "json", JS_FEED, idx + ln if ln else None,
                    "window.PS_FEED 后面不是合法 JSON：%s" % getattr(e, "msg", e))


# ---------------------------------------------------------------- 3. links

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]*)\)")
# 参考式链接定义：行首最多 3 个空格的 [label]: target（[^1]: 是脚注，不算）
REF_DEF_RE = re.compile(r"^ {0,3}\[([^\]]+)\]:[ \t]*(.*)$")
# HTML 的 <a href="…"> 和 <img src="…">，单双引号都认
HTML_LINK_RE = re.compile(
    r"""<(?:a\b[^>]*?\shref|img\b[^>]*?\ssrc)\s*=\s*(?:"([^"]*)"|'([^']*)')""",
    re.IGNORECASE)
CODE_SPAN_RE = re.compile(r"(`+).*?\1")
SKIP_SCHEMES = ("http://", "https://", "mailto:", "tel:", "#")
# 不查链接：archive/ 里是故意的占位链接；其余是机器人每天用模型生成的，写坏了谁也不该手改，报 ERROR 只会卡住当天所有口令
LINK_EXCLUDE = ("archive/", "inbox/designs/", "inbox/candidates.md", "inbox/prefilter.md")


def clean_target(raw):
    t = raw.strip()
    if t.startswith("<"):
        end = t.find(">")
        t = t[1:end] if end != -1 else t[1:]
    else:
        parts = t.split()
        t = parts[0] if parts else ""   # 去掉可选标题 "..."
    return t.strip()


FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")


def fence_step(ln, fence):
    """围栏状态机。fence 为 None（不在围栏里）或 (字符, 长度)。

    只有同一种字符、长度不小于开围栏、后面只剩空白的行才能关上；
    围栏里出现另一种字符不切换状态。返回 (新状态, 这一行是不是围栏行)。
    """
    m = FENCE_OPEN_RE.match(ln)
    if fence is None:
        if m:
            return (m.group(1)[0], len(m.group(1))), True
        return None, False
    if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
            and not ln[m.end():].strip():
        return None, True
    return fence, False


def resolve_link(ctx, md_path, t):
    """把链接目标规范化成相对仓库根的 posix 路径，按 git 文件集合判定。

    返回 None 表示存在；否则返回 ERROR 消息。
    """
    if t.startswith("/"):
        joined = t.lstrip("/")                      # GitHub 上 / 开头指仓库根
    else:
        joined = posixpath.join(posixpath.dirname(md_path), t)
    norm = posixpath.normpath(joined) if joined else "."
    if norm == ".":
        norm = ""
    if norm == ".." or norm.startswith("../"):
        return "链接指向仓库外：%s" % t
    if norm in ctx.files_set or norm in ctx.dirs_set:
        return None
    real = ctx.lower_map.get(norm.lower())
    if real is not None:
        return "大小写不对：应为 %s" % real
    return "链接目标不存在（或被 git 忽略）：%s" % t


def line_link_targets(ln):
    """一行里的链接目标：内联 [text](target)、参考式定义、<a href> / <img src>。"""
    targets = [clean_target(m.group(1)) for m in LINK_RE.finditer(ln)]
    m = REF_DEF_RE.match(ln)
    if m and not m.group(1).startswith("^"):
        targets.append(clean_target(m.group(2)))
    for m in HTML_LINK_RE.finditer(ln):
        value = m.group(1) if m.group(1) is not None else m.group(2)
        targets.append(value.strip())
    return targets


def rule_links(ctx, rep):
    for p in ctx.existing:
        if not p.endswith(".md") or p.startswith(LINK_EXCLUDE):
            continue
        text = ctx.read_text(p)
        if text is None:
            continue
        fence = None
        for i, ln in enumerate(split_lines(text), 1):
            fence, is_fence_line = fence_step(ln, fence)
            if is_fence_line or fence is not None:
                continue
            ln = CODE_SPAN_RE.sub("", ln)
            for t in line_link_targets(ln):
                if not t:
                    continue
                low = t.lower()
                if low.startswith(SKIP_SCHEMES) or "://" in t:
                    continue
                t = t.split("#", 1)[0].split("?", 1)[0]
                t = unquote(t)
                if not t:
                    continue
                problem = resolve_link(ctx, p, t)
                if problem:
                    rep.add("ERROR", "links", p, i, problem)


# ---------------------------------------------------------------- 4. experiments-list

EXP_RE = re.compile(r"^experiments/[^/]+\.md$")
README_EXP_LINK = re.compile(r"\]\((experiments/[^)\s/]+\.md)\)")
READMES = ("README.md", "README.en.md")


def exp_pages(ctx):
    # .en.md 是中文页的英文翻译，.zh.md 是英文页的中文翻译，都不算新实验
    return sorted(p for p in ctx.existing
                  if EXP_RE.match(p) and p != TEMPLATE
                  and not p.endswith((".en.md", ".zh.md")))


def rule_experiments_layout(ctx, rep):
    for p in ctx.existing:
        if p.startswith("experiments/") and not EXP_RE.match(p):
            rep.add("ERROR", "experiments-list", p, None,
                    "experiments/ 下只能放一层的 <名字>.md")


def rule_experiments_list(ctx, rep, exp):
    for readme in READMES:
        text = ctx.read_text(readme) if (ROOT / readme).is_file() else None
        listed = {}
        for i, ln in enumerate(visible_lines(text or ""), 1):
            if ln.lstrip().startswith("|"):
                for m in README_EXP_LINK.finditer(ln):
                    listed.setdefault(m.group(1), i)
        for page in exp:
            if page not in listed:
                rep.add("ERROR", "experiments-list", readme, None,
                        "%s 没进 %s 清单" % (page, readme))
        for page, i in sorted(listed.items()):
            if not (ROOT / page).is_file():
                rep.add("ERROR", "experiments-list", readme, i,
                        "清单里的 %s 不存在" % page)


# ---------------------------------------------------------------- 5. count

# 中文：「17 个实验」「每个实验一页（17 个）」
COUNT_ZH = re.compile(
    r"(?<![\d第])(?<!第 )(\d+)\s*个实验(?!室)"
    r"|每个实验一页[（(]\s*(\d+)\s*个[）)]")
# 英文：「17 experiments」「One page per experiment (17 pages)」
COUNT_EN = re.compile(
    r"\b(\d+)\s+experiments\b"
    r"|\bper experiment\s*\(\s*(\d+)\s+pages?\s*\)",
    re.IGNORECASE)
COUNT_FILES = (
    ("README.md", COUNT_ZH),
    ("MANIFESTO.md", COUNT_ZH),
    ("README.en.md", COUNT_EN),
    ("MANIFESTO.en.md", COUNT_EN),
)


def rule_count(ctx, rep, exp):
    n = len(exp)
    for path, rx in COUNT_FILES:
        text = ctx.read_text(path) if (ROOT / path).is_file() else None
        hits = 0
        # 只去掉注释；代码块（比如 README 的目录树）看得见，里面的数字也要对
        for i, ln in enumerate(visible_lines(text or "", keep_fences=True), 1):
            for m in rx.finditer(ln):
                hits += 1
                num = int(m.group(1) or m.group(2))
                if num != n:
                    rep.add("ERROR", "count", path, i,
                            "写的是 %d 个实验，实际 experiments/ 有 %d 页" % (num, n))
        if hits == 0:
            rep.add("WARN", "count", path, None, "没找到实验计数，模式可能过时")


# ---------------------------------------------------------------- 6. template

META_KEYS = ("**需要**", "**时间**", "**花费**", "**难度**", "**验收**")
TITLE_ITEM = "# 标题"


def template_headings(ctx):
    path = ROOT / TEMPLATE
    if not path.is_file():
        return None
    try:
        text = path.read_bytes().decode("utf-8", "replace").lstrip("\ufeff")
    except OSError:
        return None
    reqs = []
    for ln in visible_lines(text):
        if ln.startswith("## "):
            req = ln.rstrip()
            parts = [x.strip() for x in req[3:].split(" / ") if x.strip()]
            reqs.append((req, parts))
    return reqs


def page_missing(text, reqs):
    lines = visible_lines(text)
    missing = []
    if not first_nonempty(lines).startswith("# "):
        missing.append(TITLE_ITEM)
    table = [ln for ln in lines if ln.lstrip().startswith("|")]
    for key in META_KEYS:
        if not any(key in ln for ln in table):
            missing.append(key)
    h2 = [ln for ln in lines if ln.startswith("## ")]
    for req, parts in reqs:
        if not any(h.startswith("## " + part) for h in h2 for part in parts):
            missing.append(req)
    return missing


def parse_baseline(text):
    """返回 {页面: [缺失项]}；格式不对抛 ValueError。"""
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("顶层不是对象")
    tm = obj.get("template_missing", {})
    if not isinstance(tm, dict):
        raise ValueError("template_missing 不是对象")
    out = {}
    for page, items in tm.items():
        if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
            raise ValueError("%s 的值不是字符串列表" % page)
        out[page] = list(items)
    return out


def load_baseline(rep):
    path = ROOT / BASELINE
    if not path.is_file():
        return {}
    try:
        # utf-8-sig：带 BOM 由 rule_json 单独报，这里不因 BOM 把欠账全展开成 ERROR
        return parse_baseline(path.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        rep.add("ERROR", "template", BASELINE, None,
                "基线文件读不了，按空基线处理：%s" % e)
        return {}


def compute_template_missing(ctx, exp):
    reqs = template_headings(ctx)
    if reqs is None:
        return None
    result = {}
    for page in exp:
        text = ctx.read_text(page)
        if text is None:
            continue
        miss = page_missing(text, reqs)
        if miss:
            result[page] = miss
    return result


def rule_template(ctx, rep, exp, changed=None):
    """changed：--base 时是改动范围 {路径: 状态}，否则 None。"""
    actual = compute_template_missing(ctx, exp)
    if actual is None or not template_headings(ctx):
        rep.add("ERROR", "template", TEMPLATE, None,
                "模板不存在或没有 ## 标题，无法检查页面结构")
        return
    baseline = load_baseline(rep)
    for page in exp:
        miss = actual.get(page, [])
        known = baseline.get(page, [])
        for item in miss:
            if item in known:
                rep.add("WARN", "template", page, None,
                        "缺 %s（已知欠账，见 baseline）" % item)
            else:
                rep.add("ERROR", "template", page, None, "缺 %s" % item)
        for item in known:
            if item not in miss:
                if changed is not None and page in changed:
                    # 棘轮：这次改了这页又补齐了，就得顺手从 baseline 删掉
                    rep.add("ERROR", "template", page, None,
                            "%s 已补齐，从 baseline 删掉这一条" % item)
                else:
                    rep.add("INFO", "template", page, None,
                            "%s 已补齐，可从 baseline 删掉" % item)
    exp_set = set(exp)
    for page in sorted(baseline):
        if page not in exp_set and baseline[page]:
            rep.add("INFO", "template", page, None,
                    "页面已不在，可从 baseline 删掉")


# ---------------------------------------------------------------- 7. drafts

DRAFT_RE = re.compile(r"^inbox/designs/[^/]+\.md$")
DRAFT_MARK = "> \u26a0\ufe0f"  # "> ⚠️"


# ---------------------------------------------------------------- 6b. provenance

PROV_HEADING = "## 来源与依据"


def rule_provenance(ctx, rep):
    """审计要求：每个实验页必须有「来源与依据」，且至少 2 条可点开的外链。"""
    for page in exp_pages(ctx):
        text = ctx.read_text(page)
        if text is None:
            continue
        m = re.search(r"^" + re.escape(PROV_HEADING) + r"\s*$", text, re.M)
        if not m:
            rep.add("ERROR", "provenance", page, None,
                    "缺 %s（审计要求：每页必须有可点开的来源，至少 2 条）" % PROV_HEADING)
            continue
        tail = text[m.end():]
        nxt = tail.find("\n## ")
        if nxt != -1:
            tail = tail[:nxt]
        links = re.findall(r"\]\((https?://[^)\s]+)\)", tail)
        if len(links) < 2:
            rep.add("ERROR", "provenance", page, None,
                    "来源少于 2 条（现在 %d 条）；审计要求每页可回溯" % len(links))


def rule_drafts(ctx, rep):
    for p in ctx.existing:
        if not DRAFT_RE.match(p) or p == "inbox/designs/README.md":
            continue
        text = ctx.read_text(p)
        if text is None:
            continue
        if not first_nonempty(split_lines(text)).startswith(DRAFT_MARK):
            rep.add("WARN", "drafts", p, None, "草稿没有可见的『未核对』标注")


# ---------------------------------------------------------------- 8. scope

# inbox/ 直接下的任何 *.json 都是机器人文件（inbox/designs/ 这种子目录不算）
BOT_JSON_RE = re.compile(r"^inbox/[^/]+\.json$")
BOT_FILES = {
    "inbox/prefilter.md", "inbox/candidates.md", "inbox/.ai-error",
    "feed/latest.json", "feed/latest.js", "collector/seen.json",
}
OWNER_FILES = {"CHARTER.md", "CHARTER.en.md", "MANIFESTO.md",
               "MANIFESTO.en.md", "LICENSE"}
OWNER_PREFIXES = ("archive/",)
# 规则和闸门本身：Claude 审 + 主人拍板
GATE_FILES = {"AGENTS.md", "CLAUDE.md", "maintenance/check.py",
              ".gitignore", ".gitattributes"}
GATE_PREFIXES = (".github/",)
CLAUDE_FILES = {"SKILL.md"}
CLAUDE_PREFIXES = ("collector/", "maintenance/", "experiments/")
DRAFT_DIR = "inbox/designs/"
DRAFT_README = "inbox/designs/README.md"


def is_bot_file(path):
    return path in BOT_FILES or BOT_JSON_RE.match(path) is not None


def is_gate_file(path):
    return path in GATE_FILES or path.startswith(GATE_PREFIXES)


def needs_owner(path):
    return path in OWNER_FILES or path.startswith(OWNER_PREFIXES)


def needs_claude(path):
    return path in CLAUDE_FILES or path.startswith(CLAUDE_PREFIXES)


def check_ref(ref):
    if not ref or ref.startswith("-"):
        raise EnvError("--base 的 ref 不合法：%r" % ref)
    r = git(["rev-parse", "--verify", "--quiet", ref + "^{commit}"],
            ok_codes=(0, 1, 128))
    if r.returncode != 0:
        raise EnvError("--base 的 ref 不存在：%s" % ref)


def merge_base(ref):
    return git(["merge-base", ref, "HEAD"]).stdout.decode("utf-8", "replace").strip()


def changed_files(ref):
    """相对 ref 的改动范围：{路径: "A" / "M" / "D"}。

    合并 已提交（ref...HEAD）、暂存、未暂存、未跟踪 四个来源。
    只有最终工作区里文件不存在时才算删除（D）。
    """
    sources = [
        ["diff", "--name-status", "--no-renames", "-z", ref + "...HEAD", "--"],
        ["diff", "--name-status", "--no-renames", "-z", "--cached"],
        ["diff", "--name-status", "--no-renames", "-z"],
    ]
    seen = {}
    for args in sources:
        parts = split_z(git(args).stdout)
        for k in range(0, len(parts) - 1, 2):
            seen.setdefault(parts[k + 1], set()).add(parts[k][:1])
    for p in split_z(git(["ls-files", "--others", "--exclude-standard",
                          "-z"]).stdout):
        seen.setdefault(p, set()).add("A")
    out = {}
    for p, sts in seen.items():
        if p.startswith(".tmp/"):
            # .tmp/ 不碰：不去文件系统看，只按 git 给的状态
            gone = sts == {"D"}
        else:
            gone = not os.path.lexists(str(ROOT / p))
        if gone:
            out[p] = "D"
        elif "A" in sts:
            out[p] = "A"
        else:
            out[p] = "M"
    return out


def patch_added_secret_paths(patch):
    """在 diff 文本的新增行里找疑似密钥，返回命中的文件路径集合（不返回值）。"""
    hits = set()
    cur = None
    in_hunk = False
    for ln in split_lines(patch):
        if ln.startswith("diff --git "):
            cur = None
            in_hunk = False
            continue
        if not in_hunk:
            if ln.startswith("+++ "):
                t = ln[4:]
                if t.startswith('"') and t.endswith('"') and len(t) >= 2:
                    t = t[1:-1]
                cur = t[2:] if t.startswith("b/") else t
            elif ln.startswith("@@"):
                in_hunk = True
            continue
        if ln.startswith("+") and has_secret(ln[1:]):
            hits.add(cur)
    return hits


def scan_history(rep, mb):
    """扫 mb..HEAD 每个提交的新增行和提交信息。绝不打印命中的值。"""
    shas = split_lines(git(["rev-list", "--reverse", mb + "..HEAD"]).stdout
                       .decode("utf-8", "replace"))
    diff_opts = ["--no-color", "--no-ext-diff", "--no-textconv", "--no-renames",
                 "--src-prefix=a/", "--dst-prefix=b/"]
    for sha in shas:
        sha = sha.strip()
        if not sha:
            continue
        short = sha[:7]
        hits = set()
        msg = git(["log", "-1", "--format=%B", sha]).stdout.decode("utf-8", "replace")
        if any(has_secret(ln) for ln in split_lines(msg)):
            hits.add(None)
        parents = git(["rev-list", "--parents", "-n", "1", sha]).stdout \
            .decode("utf-8", "replace").split()[1:]
        if parents:
            # 合并提交跟第一个父提交比：冲突解决里塞进来的东西也扫得到
            args = ["-c", "core.quotePath=false", "diff"] + diff_opts \
                + ["-p", parents[0], sha, "--"]
        else:
            args = ["-c", "core.quotePath=false", "show", "--format="] + diff_opts \
                + ["-p", sha, "--"]
        hits |= patch_added_secret_paths(
            git(args).stdout.decode("utf-8", "replace"))
        for path in sorted(hits, key=lambda x: (x is not None, x or "")):
            rep.add("ERROR", "secrets", path, None,
                    "提交 %s 的历史里有疑似密钥（值已隐藏）" % short)


def rule_scope(ctx, rep, ref, changed):
    if not changed:
        rep.add("ERROR", "scope", None, None,
                "相对 %s 没有任何改动（改动没写进去？）" % ref)
    branch = git(["symbolic-ref", "--short", "-q", "HEAD"],
                 ok_codes=(0, 1)).stdout.decode("utf-8", "replace").strip()
    if branch == "main":
        rep.add("ERROR", "scope", None, None,
                "当前在 main 分支上：改动要在 dsh/ 分支上做")

    mb = merge_base(ref)
    scan_history(rep, mb)

    need_claude = need_owner = False
    for p in sorted(changed):
        st = changed[p]
        if is_bot_file(p):
            rep.add("ERROR", "scope", p, None, "机器人每天重写的文件，别手改")
        elif p == BASELINE:
            if scope_baseline(rep, mb, st):
                need_claude = True
        elif is_gate_file(p):
            need_claude = need_owner = True
            rep.add("REVIEW", "scope", p, None, "需要 Claude 审 + 主人拍板")
        elif needs_owner(p):
            need_owner = True
            rep.add("REVIEW", "scope", p, None, "需要主人拍板")
        elif p.lower().startswith(DRAFT_DIR):
            # inbox/designs/ 下任何文件（不限扩展名、不分大小写）
            if st == "D" and p.lower() != DRAFT_README.lower():
                rep.add("INFO", "scope", p, None, "删草稿")
            else:
                need_claude = True
                rep.add("REVIEW", "scope", p, None, "草稿内容变了，需要 Claude 审")
        elif needs_claude(p):
            need_claude = True
            rep.add("REVIEW", "scope", p, None, "需要 Claude 审（物理/安全/代码）")
        else:
            rep.add("INFO", "scope", p, None, "机械改动")
        if st != "D" and p in ctx.secret_skipped:
            rep.add("WARN", "secrets", p, None, "没扫密钥（文件太大或是二进制）")

    if rep.items["ERROR"]:
        summary = "先修掉 ERROR（修好之前不能开 PR）"
    else:
        needs = []
        if need_claude:
            needs.append("Claude 审")
        if need_owner:
            needs.append("主人拍板")
        if not needs:
            needs.append("只需 check 全绿")
        summary = " / ".join(needs)
    rep.add("INFO", "scope", None, None, "这次改动需要：" + summary)


def baseline_diff(old, new):
    """old / new 都是 dict。返回 (新增条目列表, 是否有「删条目」以外的改动)。"""
    other = set(old) != set(new)
    for k in set(old) & set(new):
        if k != "template_missing" and old[k] != new[k]:
            other = True
    old_tm = old.get("template_missing", {})
    if not isinstance(old_tm, dict):
        old_tm = {}
    new_tm = new.get("template_missing", {})
    added = []
    if not isinstance(new_tm, dict):
        return added, True
    for page in sorted(new_tm):
        items = new_tm[page]
        if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
            other = True
            continue
        if page not in old_tm and not items:
            other = True                       # 新加了一个空的页面键
        before = old_tm.get(page, [])
        remaining = list(before) if isinstance(before, list) else []
        for item in items:
            if item in remaining:
                remaining.remove(item)
            else:
                added.append("%s %s" % (page, item))
    return added, other


def scope_baseline(rep, mb, status):
    """baseline 跟 merge-base 比。返回 True 表示需要 Claude 审。"""
    path = ROOT / BASELINE
    if status == "D" or not path.is_file():
        rep.add("ERROR", "scope", BASELINE, None, "baseline 不能删")
        return False
    spec = "%s:%s" % (mb, BASELINE)
    if git(["cat-file", "-e", spec], ok_codes=(0, 1, 128)).returncode != 0:
        rep.add("REVIEW", "scope", BASELINE, None, "baseline 是新加的，需要 Claude 审")
        return True
    old = {}
    r = git(["show", spec], ok_codes=(0, 128))
    if r.returncode == 0:
        try:
            old = json.loads(r.stdout.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError):
            old = {}
    if not isinstance(old, dict):
        old = {}
    try:
        new = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        new = None
    if not isinstance(new, dict):
        rep.add("ERROR", "scope", BASELINE, None, "baseline 读不了，没法比较")
        return False
    added, other = baseline_diff(old, new)
    for a in added:
        rep.add("ERROR", "scope", BASELINE, None,
                "baseline 只能删不能加：新增了 %s" % a)
    if other:
        rep.add("REVIEW", "scope", BASELINE, None,
                "baseline 除了删条目还有别的改动，需要 Claude 审")
        return True
    if not added:
        rep.add("INFO", "scope", BASELINE, None, "baseline 只删不加")
    return False


# ---------------------------------------------------------------- 输出

def fmt_item(level, it):
    loc = it["path"] if it["path"] is not None else "-"
    if it["line"] is not None:
        loc = "%s:%d" % (loc, it["line"])
    return "%s  %s  %s  %s" % (level, it["rule"], loc, it["message"])


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="check.py", description="机械体检（只读）。退出码 0 = 没有 ERROR，1 = 有 ERROR，2 = 用法/环境问题。")
    ap.add_argument("--base", metavar="REF",
                    help="额外检查相对 REF 的改动范围，例如 origin/main")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    rep = Report()
    try:
        ctx = Context()
        changed = None
        if args.base is not None:
            check_ref(args.base)
            changed = changed_files(args.base)
        exp = exp_pages(ctx)
        rule_secrets(ctx, rep)
        rule_json(ctx, rep)
        rule_links(ctx, rep)
        rule_experiments_layout(ctx, rep)
        rule_experiments_list(ctx, rep, exp)
        rule_count(ctx, rep, exp)
        rule_template(ctx, rep, exp, changed)
        rule_provenance(ctx, rep)
        rule_drafts(ctx, rep)
        if args.base is not None:
            rule_scope(ctx, rep, args.base, changed)
    except EnvError as e:
        print("check: %s" % e, file=sys.stderr)
        return 2

    counts = {"error": len(rep.items["ERROR"]), "warn": len(rep.items["WARN"]),
              "review": len(rep.items["REVIEW"]), "info": len(rep.items["INFO"])}
    if args.json:
        out = {"errors": rep.items["ERROR"], "warnings": rep.items["WARN"],
               "review": rep.items["REVIEW"], "info": rep.items["INFO"],
               "summary": counts}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for lv in LEVELS:
            for it in rep.items[lv]:
                print(fmt_item(lv, it))
        print("check: %d error, %d warn, %d review, %d info"
              % (counts["error"], counts["warn"], counts["review"], counts["info"]))
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
