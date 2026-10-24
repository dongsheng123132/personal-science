# 采集 + 筛选：这套东西怎么跑

## 分工

| 谁 | 干什么 | 为什么这么分 |
|---|---|---|
| `collect.py` | 撒网、去重、打分、写文件 | 机器擅长重复劳动，不擅长判断 |
| `triage.py` | 用模型从 `raw.json` 里挑出能做的，写 `candidates.md` | 判断"一个人能不能做"需要常识，关键词做不到 |
| 人 | 决定写哪一页、怎么提 PR | 清单只进能照着做的，这一关不能自动化 |

**不要让脚本决定清单内容。** 脚本只负责"今天有哪些新东西"，AI 和人才负责"哪个值得写"。

## 每天跑什么

```bash
python collector/collect.py
python collector/triage.py    # 需要 PS_LLM_KEY；没有就自动跳过，不影响别的
```

产出：

| 文件 | 是什么 |
|---|---|
| `inbox/raw.json` | 今天抓到的全部内容（90 条左右），带分数和命中的关键词 |
| `inbox/prefilter.md` | 按分数排的前 30 条，快速扫一眼用 |
| `inbox/candidates.md` | AI 筛完的 8 条 + 筛掉理由（没配 key 时不动这个文件） |
| `feed/latest.json` / `latest.js` | 给网页看板用 |
| `collector/seen.json` | 去重库，见过的不再出现 |

## AI 筛选（已经自动化）

`triage.py` 读 `raw.json`、调模型、直接写 `candidates.md`。GitHub Actions 里已经接好了：

- 配了 `PS_LLM_KEY` → 每天自动跑
- 没配 → 打印一句提示跳过，采集和提交照常

prompt 在 `triage.py` 顶部，想改判断标准就改那里。

想手动跑也行，把下面这段发给任何能读长文本的 AI：

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

**1. 本地种子库（经典实验）** — `collector/classics.json`

年代不限的经典实验，一条一个对象：`zh` / `en` / `era` / `what` / `redo` / `tools` / `why` / `level`。
它不会被"去重"掉，也不按年代扣分——经典本来就是用来重做的。

**2. 维基百科搜索** — 经典实验、思想实验、科学史条目

```json
"wikipedia": { "sites": ["zh.wikipedia.org", "en.wikipedia.org"],
               "queries": ["经典实验 物理", "thought experiment"], "limit": 6 }
```

走 MediaWiki 的 `generator=search`，不需要 key。天然"不限年代"。

**3. WordPress 站点的搜索接口**（最准，Hackaday 就是这么接的）

```json
"wordpress": {
  "sites": ["https://hackaday.com"],
  "queries": ["spectrometer", "microscope"],
  "per_query": 5
}
```

接口是 `/wp-json/wp/v2/posts?search=关键词`。很多科技/创客博客都是 WordPress，直接把域名丢进去就能用。

**4. RSS / Atom**

```json
"feeds": { "feeds": [{ "name": "xxx", "url": "https://xxx/feed/", "enabled": true }] }
```

**5. 有公开 API 的**（GitHub / HN / arXiv）

代码里已经写好了，`sources.json` 里把 `enabled` 打开就行。

## 年代怎么处理

- 新闻型来源（RSS / WordPress / HN）：照常按新鲜度加分，太旧的降权。
- 经典型和维基条目：标记 `timeless`，**不看年代，不加分也不扣分**，并且在池子里永久保留。
- 池子按"抓到的日期"滚动（30 天），不按"发布年代"——否则一百年前的实验进来就被清掉了。

## 一句话

**脚本负责"看得多"，AI 负责"看得准"，人负责"做得完"。**
