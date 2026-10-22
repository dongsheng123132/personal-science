#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitScience 索引器 v0.1

扫描带 gitscience-* topic 的 GitHub 仓库（或本地 examples/），校验格式，
生成网站数据。纯标准库，无依赖。

用法:
    python indexer/gitscience.py check --local examples
    python indexer/gitscience.py build --local examples --out site
    set GITHUB_TOKEN=ghp_xxx
    python indexer/gitscience.py build --github --out site

设计原则: 只统计事实，不打分、不排序、不判真假。
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"
PROTOCOL = "0.1"
KIND_FILES = {"lab": "lab.json", "experiment": "exp.json", "reproduction": "rep.json"}
TOPICS = ["gitscience-lab", "gitscience-exp", "gitscience-rep"]
BLOCKED_TOPICS = [
    "gitscience-bio",
    "gitscience-radiation",
    "gitscience-explosive",
    "gitscience-drug",
]

# ---------------------------------------------------------------- 最小 schema 校验


def _type_ok(value, want):
    if want == "object":
        return isinstance(value, dict)
    if want == "array":
        return isinstance(value, list)
    if want == "string":
        return isinstance(value, str)
    if want == "boolean":
        return isinstance(value, bool)
    if want == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if want == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def validate(value, schema, path="$"):
    errs = []
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: 应为 {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} 不在 {schema['enum']}")

    t = schema.get("type")
    if t and not _type_ok(value, t):
        return errs + [f"{path}: 类型应为 {t}"]

    if t == "object":
        for req in schema.get("required", []):
            if req not in value:
                errs.append(f"{path}: 缺少必填字段 '{req}'")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errs.extend(validate(value[key], sub, f"{path}.{key}"))

    elif t == "array":
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: 至少需要 {schema['minItems']} 项")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                errs.extend(validate(item, item_schema, f"{path}[{i}]"))

    elif t == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(f"{path}: 至少 {schema['minLength']} 个字符")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{path}: 最多 {schema['maxLength']} 个字符")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: {value!r} 不匹配 {schema['pattern']}")

    elif t in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: 不能小于 {schema['minimum']}")

    return errs


def load_schemas():
    return {
        kind: json.loads((SCHEMA_DIR / f"{kind[:3]}.schema.json").read_text("utf-8"))
        for kind in KIND_FILES
    }


# ---------------------------------------------------------------- 读取


def read_json(path):
    return json.loads(Path(path).read_text("utf-8"))


def scan_local(root):
    """example 布局: <root>/<owner>/<repo>/...，任意深度的 lab/exp/rep.json。"""
    root = Path(root)
    found = []
    for path in sorted(root.rglob("*.json")):
        if path.name not in KIND_FILES.values():
            continue
        rel = path.relative_to(root).parts
        if len(rel) < 2:
            continue
        owner, repo = rel[0], rel[1]
        found.append({
            "path": path,
            "owner": owner,
            "repo": repo,
            "rel": "/".join(rel[2:]),
            "stars": None,
            "topics": [],
        })
    return found


def github_get(url, token=None):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "gitscience-indexer",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_raw(owner, repo, branch, path):
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "gitscience-indexer"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def scan_github(token=None, max_pages=3):
    repos, seen = [], set()
    for topic in TOPICS:
        for page in range(1, max_pages + 1):
            q = f"https://api.github.com/search/repositories?q=topic:{topic}&per_page=100&page={page}"
            try:
                payload = github_get(q, token)
            except urllib.error.HTTPError as exc:
                print(f"  ! 搜索 {topic} 第 {page} 页失败: {exc.code}", file=sys.stderr)
                break
            items = payload.get("items", [])
            for item in items:
                full = item["full_name"]
                if full in seen:
                    continue
                seen.add(full)
                owner, repo = full.split("/", 1)
                repos.append({
                    "owner": owner,
                    "repo": repo,
                    "branch": item.get("default_branch", "main"),
                    "stars": item.get("stargazers_count", 0),
                    "topics": item.get("topics", []),
                })
            if len(items) < 100:
                break

    print(f"  找到 {len(repos)} 个带 topic 的仓库")
    found = []
    for repo in repos:
        blocked = [t for t in repo["topics"] if t in BLOCKED_TOPICS]
        if blocked:
            print(f"  - 跳过 {repo['owner']}/{repo['repo']}（{', '.join(blocked)}）")
            continue
        full = f"{repo['owner']}/{repo['repo']}"
        try:
            tree = github_get(
                f"https://api.github.com/repos/{full}/git/trees/{repo['branch']}?recursive=1",
                token,
            )
        except urllib.error.HTTPError as exc:
            print(f"  ! 读取 {full} 目录失败: {exc.code}", file=sys.stderr)
            continue
        for node in tree.get("tree", []):
            path = node["path"]
            if Path(path).name not in KIND_FILES.values():
                continue
            try:
                data = fetch_raw(repo["owner"], repo["repo"], repo["branch"], path)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! 读取 {full}/{path} 失败: {exc}", file=sys.stderr)
                continue
            found.append({
                "path": None,
                "data": data,
                "owner": repo["owner"],
                "repo": repo["repo"],
                "rel": path,
                "stars": repo["stars"],
                "topics": repo["topics"],
            })
    return found


# ---------------------------------------------------------------- 组装


def parent_id(rel):
    """experiments/foo/exp.json -> foo; reproductions/bar/rep.json -> bar"""
    parts = Path(rel).parts
    if len(parts) >= 2 and parts[-1] in KIND_FILES.values():
        return parts[-2]
    return None


def build_index(entries, source, stars_map=None, schemas=None):
    schemas = schemas or load_schemas()
    stars_map = stars_map or {}

    labs, exps, reps, warnings = [], [], [], []

    def warn(msg):
        warnings.append(msg)
        print(f"  ! {msg}", file=sys.stderr)

    for entry in entries:
        owner, repo, rel = entry["owner"], entry["repo"], entry["rel"]
        key = f"{owner}/{repo}"
        where = f"{key}/{rel}"
        try:
            data = entry.get("data") if entry.get("data") is not None else read_json(entry["path"])
        except Exception as exc:  # noqa: BLE001
            warn(f"{where}: 读不了 JSON（{exc}）")
            continue

        kind = data.get("kind")
        if kind not in KIND_FILES:
            warn(f"{where}: kind 必须是 lab / experiment / reproduction")
            continue

        errs = validate(data, schemas[kind])
        if errs:
            warn(f"{where}: 格式不合格，已跳过 —— " + "；".join(errs[:4]))
            continue

        stars = entry.get("stars")
        if stars is None:
            stars = stars_map.get(key, 0)

        if kind == "lab":
            uid = f"LAB:{key}"
            labs.append({
                "uid": uid,
                "owner": owner,
                "repo": repo,
                "handle": data["handle"],
                "name": data["name"],
                "bio": data.get("bio", ""),
                "city": data["location"]["city"],
                "region": data["location"].get("region", ""),
                "country": data["location"]["country"],
                "availability": data.get("availability", {}),
                "capabilities": data["capabilities"],
                "unknowns": data.get("unknowns", []),
                "stars": stars,
                "url": f"https://github.com/{key}",
                "repo_key": key,
            })
        elif kind == "experiment":
            exp_id = data["id"]
            uid = f"EXP:{key}#{exp_id}"
            exps.append({
                "uid": uid,
                "owner": owner,
                "repo": repo,
                "repo_key": key,
                "id": exp_id,
                "title": data["title"],
                "author": data["author"],
                "date": data.get("date", ""),
                "field": data.get("field", []),
                "status": data["status"],
                "question": data["question"],
                "hypothesis": data.get("hypothesis", ""),
                "protocol": data["protocol"],
                "result": data.get("result"),
                "progress": data.get("progress", ""),
                "stars": stars,
                "url": f"https://github.com/{key}",
            })
        else:
            rid = parent_id(rel) or data["reproduces"].split("#")[-1]
            uid = f"REP:{key}/{rid}"
            reps.append({
                "uid": uid,
                "owner": owner,
                "repo": repo,
                "repo_key": key,
                "rid": rid,
                "reproduces": data["reproduces"],
                "reproducer": data["reproducer"],
                "date": data.get("date", ""),
                "independence": data["independence"],
                "outcome": data["outcome"],
                "difference": data.get("difference", ""),
                "target": None,
                "url": f"https://github.com/{key}",
            })

    # ---- 连边
    lab_by_handle = {}
    for lab in labs:
        lab_by_handle.setdefault(lab["handle"], lab)

    exp_by_uid = {e["uid"]: e for e in exps}
    exp_by_short = {}
    for e in exps:
        exp_by_short[f"{e['owner']}/{e['repo']}#{e['id']}"] = e

    for rep in reps:
        target = exp_by_short.get(rep["reproduces"])
        if not target:
            warn(f"{rep['repo_key']}: 复现指向的 {rep['reproduces']} 不在索引里")
            continue
        rep["target"] = target["uid"]
        target.setdefault("reproductions", []).append(rep["uid"])

    for lab in labs:
        lab["experiments"] = [e["uid"] for e in exps if e["author"] == lab["handle"]]
        lab["reproductions"] = [r["uid"] for r in reps if r["reproducer"] == lab["handle"]]
        lab["reproduced_count"] = sum(
            1 for e in exps if e["author"] == lab["handle"]
            for r in reps if r["target"] == e["uid"] and r["independence"] == "independent"
        )
        lab["confirmed_count"] = sum(1 for c in lab["capabilities"] if c.get("confirmed"))
        lab["draft_count"] = len(lab["capabilities"]) - lab["confirmed_count"]
        lab["experiment_count"] = len(lab["experiments"])
        lab["reproduction_count"] = len(lab["reproductions"])

    for rep in reps:
        lab = lab_by_handle.get(rep["reproducer"])
        rep["reproducer_name"] = lab["name"] if lab else rep["reproducer"]
        rep["city"] = lab["city"] if lab else ""
        rep["country"] = lab["country"] if lab else ""

    for exp in exps:
        lab = lab_by_handle.get(exp["author"])
        exp["author_name"] = lab["name"] if lab else exp["author"]
        exp["city"] = lab["city"] if lab else ""
        exp["country"] = lab["country"] if lab else ""
        rep_list = [r for r in reps if r["target"] == exp["uid"]]
        exp["reproductions"] = [r["uid"] for r in rep_list]
        exp["independent_count"] = sum(1 for r in rep_list if r["independence"] == "independent")
        exp["matched_count"] = sum(1 for r in rep_list if r["outcome"] == "matched")

    counts = {
        "labs": len(labs),
        "experiments": len(exps),
        "reproductions": len(reps),
        "independent": sum(1 for r in reps if r["independence"] == "independent"),
        "cities": len({l["city"] for l in labs if l["city"]}),
        "countries": len({l["country"] for l in labs if l["country"]}),
    }

    graph = {
        "nodes": [
            {"id": e["uid"], "kind": "experiment", "label": e["title"],
             "sub": f"{e['city']} · {e['author_name']}", "outcome": (e.get("result") or {}).get("outcome")}
            for e in exps
        ] + [
            {"id": r["uid"], "kind": "reproduction", "label": r["reproducer_name"],
             "sub": r["city"], "outcome": r["outcome"]}
            for r in reps
        ],
        "edges": [
            {"from": r["target"], "to": r["uid"], "outcome": r["outcome"]}
            for r in reps if r["target"]
        ],
    }

    meta = {
        "source": source,
    }
    if source == "demo":
        meta["note"] = "演示数据，不是真实网络"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol": PROTOCOL,
        "source": source,
        "counts": counts,
        "labs": labs,
        "experiments": exps,
        "reproductions": reps,
        "graph": graph,
        "warnings": warnings,
        **meta,
    }


# ---------------------------------------------------------------- 输出


def write_outputs(index, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(index, ensure_ascii=False, indent=2)
    (out / "index.json").write_text(payload + "\n", "utf-8")
    (out / "data.js").write_text(
        "// 由 indexer/gitscience.py 生成，勿手改\nwindow.GS_DATA = " + payload + ";\n",
        "utf-8",
    )
    print(f"\n已生成 {out/'index.json'} 和 {out/'data.js'}")
    print("  实验室 {labs} · 实验 {experiments} · 复现 {reproductions} · 独立复现 {independent}".format(**index["counts"]))
    if index["warnings"]:
        print(f"  警告 {len(index['warnings'])} 条")


def main(argv=None):
    parser = argparse.ArgumentParser(description="GitScience 索引器")
    parser.add_argument("command", choices=["check", "build"])
    parser.add_argument("--local", help="扫描本地目录（example 布局）")
    parser.add_argument("--github", action="store_true", help="扫描 GitHub topic")
    parser.add_argument("--out", default="site", help="输出目录")
    args = parser.parse_args(argv)

    if not args.local and not args.github:
        parser.error("要么 --local，要么 --github")

    if args.local:
        source = "demo" if args.local.strip("/\\").endswith("examples") else "local"
        entries = scan_local(args.local)
        stars_path = Path(args.local) / "stars.json"
        stars_map = read_json(stars_path) if stars_path.exists() else {}
    else:
        source = "github"
        entries = scan_github(os.environ.get("GITHUB_TOKEN"))
        stars_map = {}

    print(f"扫描到 {len(entries)} 个 JSON 文件")
    index = build_index(entries, source=source, stars_map=stars_map)

    if args.command == "check":
        ok = not index["warnings"]
        print(f"\n{'通过' if ok else '有问题'}: 实验室 {index['counts']['labs']} · 实验 {index['counts']['experiments']} · 复现 {index['counts']['reproductions']}")
        return 0 if ok else 1

    write_outputs(index, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
