#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 设计实验方案：从候选池里挑高分条目，让模型写一份实验页草稿。

产出在 inbox/designs/，不是正式清单——人改完再提 PR 进 experiments/。
没有 PS_LLM_KEY 时自动跳过（退出码 0），不影响定时任务。

用法:
    python collector/design.py --top 2
"""

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.request
from datetime import datetime, timezone

BASE = pathlib.Path(__file__).resolve().parent.parent
POOL_PATH = BASE / "inbox" / "pool.json"
RAW_PATH = BASE / "inbox" / "raw.json"
DESIGN_DIR = BASE / "inbox" / "designs"
DONE_PATH = BASE / "inbox" / "designed.json"
NOW = datetime.now(timezone.utc)

SYSTEM = """你是实验设计师。你的任务不是写科普，是写一份**别人能照着做、做完能判断对错**的实验页。

硬性要求：
1. 一个人在家能做：预算 ≤ ¥200（约 $30）、一个周末内、不需要资质、不涉及危险操作。
2. 必须有一个可测量的量，并且**在做之前写死验收标准**（例如"算出的 g 在 8.5–10.5 之间"）。
3. 必须有一节「AI 可以怎么帮你」，写至少 4 条，每条给出**可以直接复制给 AI 的 prompt**。
4. 必须有一节「坑」，写清最容易失败的地方。
5. 必须有一节「安全」。
6. **不许编造型号、价格、参数**。不确定就写「待核实」。
7. 年代不限——经典实验越好，因为它已经被验证过，只需要说清楚"今天怎么重做"。

风格：短句、直给、不吹。中文。"""

PROMPT = """请为下面这个候选写一页实验，严格按这个结构（Markdown）：

# 实验标题
> 一句话说清你能亲手验证什么。

| | |
|---|---|
| **需要** | 每一样东西，写清型号或"待核实" |
| **时间** | 多久 |
| **花费** | ¥多少 |
| **难度** | ★☆☆ / ★★☆ / ★★★ |
| **验收** | 做之前就能写死的成功标准 |

## 为什么值得做

## 怎么做

## AI 可以怎么帮你
（至少 4 条，每条含一句可以直接复制给 AI 的 prompt）

## 算一下 / 会看到什么

## 坑

## 想再往前一步

## 安全

候选：
- 标题：{title}
- 来源：{source}
- 日期/年代：{date}
- 摘要：{summary}
- 链接：{url}
"""


def call_llm(prompt, key, base, model):
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 2600,
    }).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def slugify(title):
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title).strip("-")
    return slug[:28] or "experiment"


def main():
    parser = argparse.ArgumentParser(description="AI 设计实验方案")
    parser.add_argument("--top", type=int, default=2, help="每天设计几个")
    args = parser.parse_args()

    key = os.environ.get("PS_LLM_KEY", "")
    base = os.environ.get("PS_LLM_BASE") or "https://api.deepseek.com"
    model = os.environ.get("PS_LLM_MODEL") or "deepseek-chat"

    if not key:
        print("没有 PS_LLM_KEY，跳过 AI 设计（这不影响采集和提交）")
        return 0

    source = POOL_PATH if POOL_PATH.exists() else RAW_PATH
    picked_path = BASE / "inbox" / "picked.json"
    if picked_path.exists():
        source = picked_path  # 优先用筛选器选中的条目
    if not source.exists():
        print("没有候选池，先跑 collect.py")
        return 0

    pool = json.loads(source.read_text("utf-8")).get("items", [])
    done = {}
    if DONE_PATH.exists():
        try:
            done = json.loads(DONE_PATH.read_text("utf-8"))
        except json.JSONDecodeError:
            done = {}

    candidates = [i for i in pool if i.get("id") not in done]
    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    picked = candidates[: args.top]
    if not picked:
        print("没有新的候选可以设计")
        return 0

    DESIGN_DIR.mkdir(parents=True, exist_ok=True)
    today = NOW.strftime("%Y-%m-%d")

    for item in picked:
        prompt = PROMPT.format(
            title=item.get("title", ""),
            source=item.get("source", ""),
            date=item.get("published") or item.get("meta", {}).get("era", "") or "未知",
            summary=(item.get("summary") or "")[:500],
            url=item.get("url", ""),
        )
        try:
            text = call_llm(prompt, key, base, model)
        except Exception as exc:  # noqa: BLE001
            print(f"设计失败，跳过「{item.get('title', '')[:30]}」：{type(exc).__name__}: {exc}",
                  file=sys.stderr)
            continue
        path = DESIGN_DIR / f"{today}-{slugify(item.get('title', ''))}.md"
        header = (
            f"<!-- 草稿：AI 生成，未经人工核对。原文：{item.get('url', '')} -->\n"
            f"<!-- 待核实：型号、价格、参数请对照原文确认后再进 experiments/ -->\n\n"
        )
        path.write_text(header + text + "\n", "utf-8")
        done[item["id"]] = today
        print(f"已生成 {path.relative_to(BASE)}")

    DONE_PATH.write_text(json.dumps(done, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"本轮设计 {len(picked)} 条，累计已设计 {len(done)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
