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
import re
import sys
import urllib.request
from datetime import datetime, timezone

BASE = pathlib.Path(__file__).resolve().parent.parent
RAW_PATH = BASE / "inbox" / "raw.json"
POOL_PATH = BASE / "inbox" / "pool.json"
OUT_PATH = BASE / "inbox" / "candidates.md"
NOW = datetime.now(timezone.utc)

SYSTEM = """你是 Personal Science 的编辑。这个仓库收集"一个人（或一个老师、一个产品经理）能用今天的工具重做一遍，并且能测出一个数"的实验。

**年代不限。** 一百年前的经典实验、二战时期的测量、几十年前的心理学实验，只要今天能用 AI / ESP32 / 手机重新做一遍，并且能启发人，都是好素材。

判断五条：
1. 重做成本：一个人在家，预算 ≤ ¥200（约 $30）、一个周末内、不需要资质、不涉及危险操作。
2. 有可测量的量：能得出一个数字，而不是只"看懂了"。
3. 能写死验收标准。
4. 启发性：能让人产生"原来我能亲手验证这个"的震动。读者包括初高中老师、上班族、产品经理。
5. 能用今天的工具升级：AI 分析数据、ESP32/手机采集、开源硬件替代昂贵仪器。

危险项（高压、激光直射、化学品入口、辐射）放到"进阶 / 仅阅读"，并写清风险。

宁可今天只出 2 条，也不要凑数。"""

PROMPT = """下面是候选池（按机器分数排序的 JSON，包含新闻、经典实验、维基条目）。请挑出最多 8 条。

输出中文 Markdown，严格按这个结构：

# 今日候选 · {date}

> AI 从候选池 **{total} 条**里筛出 N 条。判断标准见 [章程](../CHARTER.md)第四条。

## 可以直接写成实验页（N 条）

### 1. 标题
原标题：<候选里的 title 原文>
候选索引：<候选里的 i 字段，只要数字>
[→ 原文](链接)
- **年代**：1801 / 1950s / 未知
- **为什么值得做**：一句话
- **要什么**：清单（候选里没提的型号/价格写"待核实"）
- **怎么用今天的工具重做**：AI / 手机 / ESP32 / 开源硬件各能做什么
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
- **不许补充候选里没有的型号、品牌、价格、参数。需要写的时候写「待核实」，不要猜。**
- 每条的第一行必须是「原标题：<候选原样的 title>」，方便人工核对
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

    # 优先用 7 天滚动池；没有池子才退回当天 raw
    source_path = POOL_PATH if POOL_PATH.exists() else RAW_PATH
    if not source_path.exists():
        print("没有 inbox/pool.json 或 raw.json，先跑 collect.py")
        return 0

    payload = json.loads(source_path.read_text("utf-8"))
    items = payload.get("items", [])
    print(f"输入池：{source_path.name}，{len(items)} 条")
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

    # 把 AI 选中的条目单独存一份，给 design.py 用——设计要跟着筛选的判断走。
    # 只取「可以直接写成实验页」那一组：被判为"仅灵感 / 仅阅读"的不该被设计成实验页。
    direct_section = text.split("## 需要补设备")[0]
    picked_ids = [int(x) for x in re.findall(r"候选索引[：:]\s*(\d+)", direct_section)]
    picked = [kept[i] for i in picked_ids if 0 <= i < len(kept)]
    picked_path = BASE / "inbox" / "picked.json"
    picked_path.write_text(json.dumps({
        "generated_at": NOW.isoformat(timespec="seconds"),
        "count": len(picked),
        "items": picked,
    }, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"已写 {OUT_PATH}（{len(text)} 字符），选中 {len(picked)} 条给设计器")
    return 0


if __name__ == "__main__":
    sys.exit(main())
