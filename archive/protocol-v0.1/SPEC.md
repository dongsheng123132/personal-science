# GitScience 协议 v0.1

这份文档是给"想实现它的人"看的：索引器、网站、第三方客户端、AI agent。目标是把"一次实验"和"一次复现"变成机器可读、可连边、可长期存档的东西。

设计原则只有一条：**少到任何人今天下午就能遵守。**

---

## 0. 三个不

1. **不认证**：没有审核、没有评级、没有证书。协议只规定格式。
2. **不评分**：指数器只统计事实（几个实验、几条独立复现），不做加权打分。
3. **不删帖**：格式不合格不收录，但东西还在你自己仓库里，谁也拿不走。

推论：这个网络**没有成员名单**。成员名单就是"带 topic 的仓库"。

---

## 1. 加入网络 = 给仓库打 topic

| topic | 含义 | 需要的文件 |
|---|---|---|
| `gitscience-lab` | 这是一个实验室 | 根目录 `lab.json` |
| `gitscience-exp` | 这是一个实验 | 根目录 `exp.json` |
| `gitscience-rep` | 这是一条独立的复现记录 | 根目录 `rep.json` |

领域标签另加，可选，用于发现：`gitscience-electronics`、`gitscience-thermal`、`gitscience-material`、`gitscience-environment`、`gitscience-bio`、`gitscience-mechanical`。

**组织方式（二选一，索引器都支持）：**

- **A. 分散式（推荐）**：一个人 = 一个 `lab` 仓库；一个实验 = 一个单独仓库（这样能被单独 star）。
- **B. 集中式（省事）**：一个 `lab` 仓库里放 `experiments/<id>/exp.json` 和 `reproductions/<id>/rep.json`。

A 更符合 GitHub 的原生语义（repo = project，star 才有意义），B 更适合一个人有很多小实验。两种混用也行。

---

## 2. `lab.json`

```json
{
  "gitscience": "0.1",
  "kind": "lab",
  "handle": "laozhou",
  "name": "老周的维修铺",
  "bio": "手机家电维修十五年，两平米工作台。",
  "location": { "city": "长沙", "region": "湖南", "country": "CN" },
  "availability": {
    "note": "周三到周日 10:00–19:00",
    "accepts_samples": true,
    "shipping": "国内",
    "paid": true
  },
  "capabilities": [
    {
      "id": "dc-measure",
      "what": "直流电压 / 电流测量",
      "gear": ["UNI-T UT61E", "可调电源 30V/5A", "电子负载 150W"],
      "limits": ["60V 以上不做", "万用表未校准，精度按说明书"],
      "confirmed": true,
      "source": "operator"
    }
  ],
  "unknowns": ["没有示波器", "不知道电子负载能不能连电脑"],
  "links": { "contact": "issue" }
}
```

字段规则：

| 字段 | 必填 | 说明 |
|---|---|---|
| `gitscience` | 是 | 协议版本，当前 `"0.1"` |
| `kind` | 是 | 固定 `"lab"` |
| `handle` | 是 | GitHub handle，用于和实验/复现连边 |
| `name` | 是 | 展示名，≤60 字 |
| `location.city` / `.country` | 是 | 只到城市。**精确地址不写进公开文件** |
| `capabilities[]` | 是，≥1 | 能力声明，见下 |
| `capabilities[].what` | 是 | 一句话说清"能做什么" |
| `capabilities[].confirmed` | 是 | **`false` = 从照片推断、本人还没确认。** 网站上必须要有视觉区别 |
| `capabilities[].source` | 否 | `"photo"` 或 `"operator"` |
| `capabilities[].limits` | 否 | **做不到什么。比"会什么"更值钱** |
| `unknowns` | 否 | 不知道的、待确认的。允许存在不确定，这才是真实 |
| `availability` | 否 | 时段、能否收样、是否收费 |
| `links` | 否 | 联系方式统一用 `"issue"`，别在公开文件里放邮箱/手机 |

**禁止**：`level`、`score`、`rating`、`verified_by_platform` 这类字段。协议不承认任何评分。

---

## 3. `exp.json`

```json
{
  "gitscience": "0.1",
  "kind": "experiment",
  "id": "adapter-drop-12v",
  "title": "标称 12V 2A 的适配器，满载时还稳吗",
  "author": "laozhou",
  "date": "2026-11-02",
  "field": ["electronics", "power"],
  "status": "done",
  "question": "在 25% / 50% / 100% 负载下，输出电压相对空载的偏差是否超过 ±5%？",
  "hypothesis": "满载压降会超过 5%。",
  "protocol": {
    "samples": 1,
    "repeats": 3,
    "gear": ["UNI-T UT61E", "电子负载 150W"],
    "steps": [
      "空载测输出电压，记 3 次",
      "接 25% 负载，稳定 60 秒后测 3 次",
      "同上 50%、100% 负载",
      "记录室温"
    ],
    "acceptance": "同一负载点 3 次读数极差 < 0.05V 才计入平均值",
    "limits": ["只测一台样品", "室温未控，±3°C"]
  },
  "result": {
    "outcome": "supports",
    "summary": "满载 11.38V，相对空载 12.00V 压降 5.2%，刚好越过 5% 线。",
    "measurements": [
      { "load": "25%", "voltage": 11.92 },
      { "load": "50%", "voltage": 11.71 },
      { "load": "100%", "voltage": 11.38 }
    ],
    "files": ["data/load-test.csv"]
  }
}
```

字段规则：

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 本实验在本仓库内的唯一 id，小写+连字符 |
| `title` / `question` | 是 | 问题要能用一个可测量量回答 |
| `author` | 是 | 作者 GitHub handle，索引器用它挂到实验室 |
| `status` | 是 | `planned` / `running` / `done` / `blocked` |
| `protocol` | 是 | **方案。必须在数据之前提交并留时间戳**（预注册） |
| `protocol.acceptance` | 是 | **什么样的数据算合格、什么样的结果算支持/不支持**，在做之前写死 |
| `result.outcome` | done 时必填 | `supports` / `refutes` / `inconclusive` |
| `result.files` | 否 | 相对仓库根目录的原始数据文件 |

`outcome` 是作者**自己的判定**，不是平台的判定。它会原样显示，也会被复现记录检验。

**负结果必须能提交**：`refutes` 和 `inconclusive` 与 `supports` 完全同权。撤稿文化不带到这来。

---

## 4. `rep.json`

```json
{
  "gitscience": "0.1",
  "kind": "reproduction",
  "reproduces": "laozhou/adapter-drop-12v#adapter-drop-12v",
  "reproducer": "xiaoli",
  "date": "2026-11-18",
  "independence": "independent",
  "outcome": "different",
  "difference": "我的样品满载 11.52V，压降 4.0%，没到 5%，结论相反。",
  "data": ["data/2026-11-18.csv"]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `reproduces` | 是 | `"<owner>/<repo>#<exp-id>"`，指向被复现的实验 |
| `reproducer` | 是 | 复现者 handle |
| `independence` | 是 | `independent`（别人） / `self`（自己重做） / `same_gear`（同一台设备换个时间） |
| `outcome` | 是 | `matched` / `different` / `failed`（没做成） / `inconclusive`（做成了但判不了） |
| `difference` | 否 | 差在哪。写条件差异，不要写"我觉得" |

**为什么复现不走 PR？**

因为 PR 由原作者决定合不合，作者一关，复现就消失了。所以复现记录放在**复现者自己的仓库**里，用 `reproduces` 字段指过去，索引器自动连边。这样：

- 复现不受被复现者控制；
- 原作者可以永远不合并，事实仍然存在；
- 一个实验被复现多少次，是别人说了算，不是作者说了算。

这是整个协议里最重要的一条设计。

---

## 5. 索引规则

1. 按 topic 搜索仓库 → 取默认分支 → 找对应 JSON。
2. 校验 schema。**不通过 = 不收录**，记一条 warning，不影响别的仓库。
3. 连边：
   - `exp.author` → `lab.handle`（作者必须存在 lab，否则实验独挂）
   - `rep.reproduces` → `exp`（仓库 owner + 实验 id 精确匹配；匹配不上就标 `unresolved`，但记录仍然显示）
4. 统计（只数事实）：
   - 实验室：实验数、复现数、被独立复现数
   - 实验：独立复现数（`independence == "independent"`）、结果分布
   - 网络：城市数、国家数、复现边数
5. 不做：加权评分、排序推荐、真假判定。

---

## 6. 内容边界（法律与安全）

协议不限制领域，但**索引器在 v0.1 会拒绝**这些 topic 标签，并建议走线下渠道：`gitscience-bio`（涉及活体/病原）、`gitscience-radiation`、`gitscience-explosive`、`gitscience-drug`。

原因很简单：这类实验出事不是"数据不准"，是"人受伤"或"违法"。协议不该在这里装中立。

其它约定：

- 不写"检测报告""认证""合格"这类字眼，写"测量记录"。
- 不发布他人隐私（住址、电话、身份证、客户数据）。仪器序列号建议打码。
- 样品、费用、寄送由双方自行约定，平台不介入、不担保。

---

## 7. 版本

`gitscience` 字段是协议版本。v0.1 的字段只增不改；破坏性变更升到 `0.2`。索引器同时读相邻两个版本。

---

## 8. 一句话总结

**GitHub 管"有没有发生过"，协议管"发生了什么"，复现管"是不是真的"。** 三件事分开，就不需要认证。
