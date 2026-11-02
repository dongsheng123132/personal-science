#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把每日发现/候选池里的英文标题翻成中文，供中文版页面显示。

英文版（/en/）不受影响，仍然显示原文。
翻译结果缓存在 feed/translations.json，只翻没翻过的，避免重复花钱。

环境变量：
  PS_LLM_KEY / PS_LLM_BASE / PS_LLM_MODEL   （CI 里用 DeepSeek）
  本机没有上面这些时，回退到 ~/.config/magpie/providers.json 里的 OpenRouter key
"""

import json
import os
import pathlib
import sys
import urllib.request

BASE = pathlib.Path(__file__).resolve().parent.parent
OUT = BASE / "feed" / "translations.json"
BATCH = 40


def llm(prompt, timeout=180):
    key = os.environ.get("PS_LLM_KEY")
    base = os.environ.get("PS_LLM_BASE") or "https://api.deepseek.com"
    model = os.environ.get("PS_LLM_MODEL") or "deepseek-chat"
    if not key:
        p = pathlib.Path.home() / ".config/magpie/providers.json"
        if p.exists():
            for prov in json.loads(p.read_text()).get("providers", []):
                if prov.get("id") == "openrouter" and prov.get("key"):
                    key = prov["key"]
                    base = "https://openrouter.ai/api/v1"
                    model = "deepseek/deepseek-v4.1-flash"
                    break
    if not key:
        print("没有可用的 LLM key，跳过翻译")
        return None
    body = json.dumps({"model": model, "temperature": 0,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return d["choices"][0]["message"]["content"].strip()


def titles():
    out = set()
    for d in ("feed/archive", "feed/pool-archive"):
        for f in (BASE / d).glob("*.json"):
            try:
                for i in json.loads(f.read_text("utf-8")).get("items", []):
                    t = (i.get("title") or "").strip()
                    if t:
                        out.add(t)
            except json.JSONDecodeError:
                continue
    return sorted(out)


def main():
    cache = {}
    if OUT.exists():
        try:
            cache = json.loads(OUT.read_text("utf-8"))
        except json.JSONDecodeError:
            cache = {}
    todo = [t for t in titles() if t not in cache]
    print("已译 %d，待译 %d" % (len(cache), len(todo)))
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        prompt = ("把下面的英文标题翻译成简体中文，用于中文网站列表展示。"
                  "保留专有名词（型号、品牌、人名）原文；不要加解释；"
                  "只输出 JSON 数组，长度和顺序与输入一致。\n\n"
                  + json.dumps(chunk, ensure_ascii=False, indent=1))
        try:
            text = llm(prompt)
        except Exception as e:  # noqa: BLE001
            print("翻译失败：%s" % e, file=sys.stderr)
            break
        if not text:
            break
        s, e2 = text.find("["), text.rfind("]")
        try:
            arr = json.loads(text[s:e2 + 1])
        except Exception:  # noqa: BLE001
            print("解析失败，跳过这一批", file=sys.stderr)
            continue
        for src, dst in zip(chunk, arr):
            if isinstance(dst, str) and dst.strip():
                cache[src] = dst.strip()
        print("  批次 %d/%d 完成" % (i // BATCH + 1, (len(todo) + BATCH - 1) // BATCH))
    OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")
    print("写入 %s（%d 条）" % (OUT.relative_to(BASE), len(cache)))


if __name__ == "__main__":
    main()
