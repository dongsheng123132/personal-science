# 采集 + 筛选：这套东西怎么跑

## 分工

| 谁 | 干什么 | 为什么这么分 |
|---|---|---|
| `collect.py` | 撒网、去重、打分、写文件 | 机器擅长重复劳动，不擅长判断 |
| AI | 从 `inbox/raw.json` 里挑出真正能做的 | 判断"一个人能不能做"需要常识，关键词做不到 |
| 人 | 决定写哪一页、怎么提 PR | 清单只进能照着做的，这一关不能自动化 |

**不要让脚本决定清单内容。** 脚本只负责"今天有哪些新东西"，AI 和人才负责"哪个值得写"。

## 每天跑什么

```bash
python collector/collect.py
```

产出：

| 文件 | 是什么 |
|---|---|
| `inbox/raw.json` | 今天抓到的全部内容（90 条左右），带分数和命中的关键词 |
| `inbox/prefilter.md` | 按分数排的前 30 条，快速扫一眼用 |
| `feed/latest.json` / `latest.js` | 给网页看板用 |
| `collector/seen.json` | 去重库，见过的不再出现 |

## AI 筛选用的 prompt

把下面这段和 `inbox/raw.json` 一起丢给任何能读长文本的 AI：

```text
你在帮一个叫 Personal Science 的仓库筛候选。

读 inbox/raw.json，按这四条判断每一条：

1. 一个人在家能不能做完？（预算 ≤ ¥200、时间 ≤ 一个周末、不需要资质）
2. 它有没有一个"可测量的量"？（不是"好玩"，是"能测出数"）
3. 能不能提前写清验收标准？
4. 有没有危险？（高压、激光、化学品、辐射、明火 → 标红，不进清单）

输出到 inbox/candidates.md，分三组：
- 可以直接写成实验页
- 需要补设备 / 属于进阶
- 只适合当灵感

每组写：为什么值得做、要什么、能写成什么实验、验收标准、风险。
最后附一张"今天筛掉了什么、为什么"的表。

不要凑数。宁可今天只出 2 条，也不要为了填满而放宽标准。
```

## 参数在哪调

- 想加来源 → `collector/sources.json`
- 想改关键词 → `collector/collect.py` 顶部的 `OBJECTS` / `PERSONAL` / `NEGATIVE`
- 想改每天条数 → `collect.py --limit 30`

## 加一个来源

目前支持三类，照着抄就行：

**1. WordPress 站点的搜索接口**（最准，Hackaday 就是这么接的）

```json
"wordpress": {
  "sites": ["https://hackaday.com"],
  "queries": ["spectrometer", "microscope"],
  "per_query": 5
}
```

接口是 `/wp-json/wp/v2/posts?search=关键词`。很多科技/创客博客都是 WordPress，直接把域名丢进去就能用。

**2. RSS / Atom**

```json
"feeds": { "feeds": [{ "name": "xxx", "url": "https://xxx/feed/", "enabled": true }] }
```

**3. 有公开 API 的**（GitHub / HN / arXiv）

代码里已经写好了，`sources.json` 里把 `enabled` 打开就行。

## 一句话

**脚本负责"看得多"，AI 负责"看得准"，人负责"做得完"。**
