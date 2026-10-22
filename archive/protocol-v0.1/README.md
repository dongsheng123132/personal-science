# GitScience

> 把你的工作台，接进世界的证据链。

GitScience 是一个**没有平台方的实验网络**。它不认证任何人，不评价任何人的能力，不发证书，也不审核你。

它只提供四样东西：

1. 一套极小的**文件格式**：`lab.json` / `exp.json` / `rep.json`
2. 一套 GitHub **约定**：topic 标签 + 目录结构
3. 一个**索引器**：扫全网带标签的仓库，生成网站数据
4. 一个**网站**：纯静态，读索引数据

任何人不需要注册、不需要申请、不需要经过任何人同意——push 一个带 `gitscience-lab` topic 的仓库，就进入了这个网络。我们无权删除你，也无权给你打分。

---

## 为什么是 GitHub

GitHub 已经把我们想要的东西全做完了：版本、时间戳、公开可查、fork、issue、star、Actions 自动校验。不需要再造一个平台，只需要**给"实验"这件事定义格式**。

| GitHub | GitScience |
|---|---|
| User / Profile | 一个实验室（`lab.json`） |
| Repository | 一个实验（`exp.json`） |
| Issue | 想做但做不了的问题、异常、失败 |
| Fork | 我按你的方案自己也做一遍 |
| PR | 我改进了你的方案 / 我补了数据 |
| Star | 这个实验值得看 |
| Actions | 自动校格式、自动汇总 |
| Topic | **加入网络的方式** |

GitHub 没有的原语只有一个：**复现**。

star 表示"我喜欢"，不表示"我验证过"。所以这里加第三个文件 `rep.json`——一条指向别人实验的记录，标明结果是一致、不同，还是没判定。**这是整个网络唯一有信息量的东西**，也是我们不做认证却还能有可信度的全部原因。

---

## 三个对象

```
你的账号/
  lab/                       ← 你是谁、你有什么、你能做什么、不能做什么
    lab.json
    reproductions/           ← 你复现了别人的实验，记录放这
      18650-capacity/rep.json

  adapter-drop-12v/          ← 一个实验一个仓库（这样才能被单独 star）
    exp.json
    data/load-test.csv
    photos/bench.jpg
```

| 文件 | 是什么 | 谁写 |
|---|---|---|
| `lab.json` | 实验室主页：设备、能力、边界、时段、能否收样 | 本人 + AI 从照片生成草稿 |
| `exp.json` | 一次实验：问题、假设、方案、原始数据、结果 | 做实验的人 |
| `rep.json` | 一次复现：复现了谁、结果如何、差异在哪 | 复现的人 |

三个 schema 在 [`schema/`](schema/)，模板在 [`templates/`](templates/)，能跑的示例在 [`examples/`](examples/)。

---

## 加入（三种方式，都不用经过我们）

**1. 有照片就行——让 AI 帮你写**

把 [`SKILL.md`](SKILL.md) 的内容贴给任何能看图的 AI（Claude Code / Codex / ChatGPT / 本机 agent），再附上一张工作台照片。它会输出 `lab.json`、一个可发的 README，和 3–5 个"你能接的验证任务"。

**2. 手动写**

```bash
git clone https://github.com/<you>/<something>  # 或者直接新建
# 从 templates/lab 复制 lab.json，照着填
gh repo create lab --public --source=. --push
gh repo edit --add-topic gitscience-lab
```

**3. 只做实验，先不建实验室**

新建一个仓库，根目录放 `exp.json`，加上 topic `gitscience-exp`。作者字段写上你的 GitHub handle，索引器会自动把你挂上去。

> 格式不对不会被封，只是**不会进索引**。像 linter，不是裁判。

---

## 本地跑

```bash
# 校验示例数据（不需要网络）
python indexer/gitscience.py check --local examples

# 用示例数据生成网站数据
python indexer/gitscience.py build --local examples --out site

# 扫真实 GitHub（需要 token，未认证 60 次/小时不够用）
set GITHUB_TOKEN=ghp_xxx
python indexer/gitscience.py build --github --out site
```

打开 `site/index.html` 就能看。网站是单文件，没有构建步骤，没有数据库，不会挂。

---

## 我们做 / 我们不做

| 做 | 不做 |
|---|---|
| 维护格式与 schema | 认证任何人、任何设备 |
| 维护索引器和网站 | 审核成员、删帖、封号 |
| 发起全球实验倡议（challenge） | 评价谁的能力高低 |
| 给复现关系连边 | 判定谁对谁错 |
| 保证数据可追溯 | 保证数据真实 |

最后一行是必须说清楚的：**我们只能让造假变贵，不能让造假消失**。方法是预注册（方案先 merge，数据后 merge）、原始文件、独立复现数、公开可查的 hash。看到东西的人自己判断。

---

## 为什么这件事值得做

- **供给侧是真实的**：维修铺、职校实训室、创客、工厂检测角，几十万台万用表在吃灰。它们不缺设备，缺的是"要测什么"。
- **科学界已经验证过这个模式**：Many Labs、Psychological Science Accelerator、Zooniverse、GLOBE——分布式复现不是乌托邦，是成熟方法，只是还没扩展到硬件和工程测量。
- **AI 刚好把门槛打掉了**：以前"我很会做实验"这件事没法写下来，现在一张照片就能翻译成结构化能力。这是 2025 年之后才成立的入口。
- **信任可以生长**：不靠证书，靠"被几个人独立复现过"。

一句话：**民间神枪手能不能打败武状元，不该由报名表决定，该由靶纸决定。**

---

## 目录

```
README.md              这一页
SPEC.md                协议 v0.1（给想实现的人看）
SKILL.md               给 AI 的可移植技能：照片 → 实验室
INITIATIVES.md         全球倡议：我们只出题，不派活
schema/                三个 JSON Schema
templates/             可直接复制的空模板
examples/              5 个实验室、3 个实验、5 条复现（演示用）
indexer/gitscience.py  索引器（纯标准库）
site/index.html        网站（单文件）
site/data.js           索引器生成的数据（当前是预生成的演示数据）
site/preview.png       页面截图
```

## 状态

- `check` / `build --local` 已用示例数据跑通
- `build --github` 需要 `GITHUB_TOKEN`，尚未实测（首次接入前先拿一个小号仓库试一次）
- 网站是纯静态的，`site/preview.png` 就是当前渲染结果

## 用 GitHub Pages 发布（可选）

仓库 Settings → Pages → Source 选 `Deploy from a branch`，目录选 `/site`。
不需要构建，不需要服务器。

## 路线图

- [x] 协议 v0.1 + 示例网络
- [x] 索引器（本地 / GitHub 双模式）
- [x] 静态站（实验室 / 实验 / 复现图）
- [x] 倡议文档与聚合约定（INITIATIVES.md）
- [ ] GitHub Action：提交 PR 时自动校 schema
- [ ] 复现图支持时间轴（看一个结论是怎么被验证或推翻的）
- [ ] 倡议页按 `challenge` 字段自动聚合
- [ ] 移动端上传入口（拍照 → 直接生成草稿）

---

协议 [v0.1](SPEC.md) · 示例数据 · 我们只校格式，不打分
