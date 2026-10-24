#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 筛选：把 inbox/raw.json 变成人可以直接看的 inbox/candidates.md

没有配 PS_LLM_KEY 时自动跳过（退出码 0），不影响每天的定时任务。

用法:
    python collector/triage.py
    python collector/triage.py --limit 30

环境变量:
    PS_LLM_KEY    必填，没有就跳过
    PS_LLM_BASE   默认 https://api.deepseek.com（任何 OpenAI 兼容接口都行）
    PS_LLM_MODEL  默认 deepseek-chat
"""

import argparse
import json
import os
import pathlib
import sys
import urllib.request
from datetime import datetime, timezone

BASE = pathlib.Path(__file__).resolve().parent.parent
RAW_PATH = BASE / "inbox" / "raw.json"
OUT_PATH = BASE / "inbox" / "candidates.md"
NOW = datetime.now(timezone.utc)

SYSTEM = """你是 Personal Science 的编辑。这个仓库只收"一个普通人在家能做完、并且能测出一个数"的实验。

判断四条，缺一条就不要：
1. 一个人在家能做完？预算 ≤ ¥200（约 $30）、一个周末内、不需要资质、不涉及危险操作。
2. 有没有一个"可测量的量"？（不是"好玩"，是"能测出数字"）
3. 能不能在做之前写死"怎么算做成了"？
4. 有没有危险？高压、激光、化学品入口、辐射、明火 → 放到"进阶"，并写清风险。

宁可今天只出 2 条，也不要凑数。"""

PROMPT = """下面是今天抓到的候选（按机器分数排序的 JSON）。请挑出最多 8 条。

输出中文 Markdown，严格按这个结构：

# 今日候选 · {date}

> AI 从今天抓到的 **{total} 条**里筛出 N 条。判断标准见 [章程](../CHARTER.md)第四条。

## 可以直接写成实验页（N 条）

### 1. 标题
[→ 原文](链接)
- **为什么**：一句话
- **要什么**：清单
- **能写成什么实验**：一句话
- **验收**：一个能写死的标准

## 需要补设备 / 属于进阶（N 条）

（同样的结构，多写一行 **风险**）

## 只适合当灵感（N 条）

（写清楚为什么不能变成实验页）

## 今天筛掉的

一张表：类别 | 条数 | 为什么不收

最后一行写：**筛选标准不是"我感不感兴趣"，是"普通人照着能不能做一个能验收的测量"。**

注意：
- 只从下面的候选里选，不要编造项目和链接
- 链接必须原样使用候选里的 url
- 没有把握的写"不确定"，不要猜

候选数据：
{items}
"""


def call_llm(prompt, key, base, model):
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2400,
    }).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def main():
    parser = argparse.ArgumentParser(description="AI 筛选候选")
    parser.add_argument("--limit", type=int, default=40, help="送进模型的候选条数")
    args = parser.parse_args()

    key = os.environ.get("PS_LLM_KEY", "")
    base = os.environ.get("PS_LLM_BASE") or "https://api.deepseek.com"
    model = os.environ.get("PS_LLM_MODEL") or "deepseek-chat"

    if not key:
        print("没有 PS_LLM_KEY，跳过 AI 筛选（这不影响采集和提交）")
        return 0
    if not RAW_PATH.exists():
        print("没有 inbox/raw.json，先跑 collect.py")
        return 0

    payload = json.loads(RAW_PATH.read_text("utf-8"))
    items = payload.get("items", [])
    kept = items[: args.limit]
    compact = [
        {
            "i": n,
            "score": it.get("score", 0),
            "source": it.get("source", ""),
            "date": it.get("published", ""),
            "title": it.get("title", ""),
            "summary": (it.get("summary") or "")[:160],
            "url": it.get("url", ""),
        }
        for n, it in enumerate(kept)
    ]
    prompt = PROMPT.format(
        date=payload.get("date") or NOW.strftime("%Y-%m-%d"),
        total=len(items),
        items=json.dumps(compact, ensure_ascii=False, indent=1),
    )

    try:
        text = call_llm(prompt, key, base, model)
    except Exception as exc:  # noqa: BLE001
        print(f"AI 筛选失败，跳过：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 0  # 不要让定时任务因此变红

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(text + "\n", "utf-8")
    print(f"已写 {OUT_PATH}（{len(text)} 字符）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
