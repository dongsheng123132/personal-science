# 待办清单

这份清单由 Claude 维护，DSH 只读不改。三个区：

- **🟢 DSH 可以做**：每条都写死了改哪个文件、原文是什么、改成什么、怎么验收。照做，不多改一个字。
- **🧠 交给 Claude**：要判断物理、安全或代码设计的。DSH 不碰，发现新的也写进日报交过来。
- **👤 交给主人**：要拍板、要动仓库设置、要花钱的。

来源：2026-10-25 的全仓评审（流水线、实验页、文档、CI 四路审查，每条都经过复核）。

## 规则

- 编号永不复用。做完的条目不删，由 Claude 在周审时把 `[ ]` 改成 `[x]` 并写上 PR 号。
  要改写的条目（比如 DSH 放弃过的）标成 `[~]`、写「作废，见 Byy」，改好的内容用新编号 Byy 重写。
- **DSH 怎么判断一条做没做过**：按 [维护手册 §3.1](README.md#31-做一条待办口令做一条待办) 第 2 步，查有没有标题或分支名里带这个编号的 `dsh/` PR（开着的、合并的、关掉的都算）、有没有带这个编号的远端 `dsh/` 分支、日报里有没有「放弃 Bxx：」。有就跳过。
- **按原文定位，行号只是参考。** 别的条目合并后行号会挪，对不上没关系。条目里的「原文」在文件里找不到，或者出现不止一次，才**放弃这条**，在日报里写「放弃 Bxx：原文找不到」或「放弃 Bxx：原文不唯一」。不要按自己的理解改。
- 下面的代码块都缩在列表里，原始文本每行前面多 2 个空格，复制时去掉（手册 §3.1 第 4 步）。「行首 N 个空格」说的是去掉之后。
- 「在 X 这一行后面插入 Y」这类条目，X 就是原文，照样要正好出现一次；怎么插见手册 §3.1 第 4 步。
- 验收只比输出的字，不看 exit。期望输出是 `0` 或「没有输出」的 grep，exit 本来就是 1，正常。
- 条目之间有先后的，条目里写一行「依赖：Bxx」。Bxx 没合并之前不做这条。没写「依赖」的条目，和别的条目谁先谁后都行。
- 一条一个 PR。PR 标题：`[Bxx] 一句话`，check 说要审就加 `[待审]` 前缀。
- 🟢 条目不改 `.github/`、`AGENTS.md`、`CLAUDE.md`、`maintenance/`、`.gitignore`、`.gitattributes`。DSH 看到这样的条目不做，写进日报。
- 给 Claude 的写条目要求：写进 🟢 区之前，原文、改法、验收命令都要在当前 main 上实测过；原文要在文件里正好出现一次，
  第一行不能是空行、```` ``` ````、`~~~` 这种会重复的行；验收的期望输出逐字写出来，不写「左右」「目测」「同 Bxx」——DSH 只会逐字比对；
  期望输出里不能有行号（`grep -n` 有输出、`sed -n 7p` 这种都不行；期望「没有输出」的 `grep -n` 可以），
  用 `grep -c -F -- '整行' 文件` 这类和行号无关的命令，别的条目先合并也不受影响。

---

## 🟢 DSH 可以做

### [ ] B01 · collect.py 把空的模型名发给 DeepSeek，AI 推荐理由每次 400

CI 里没设 `PS_LLM_MODEL`，GitHub 传进来的是空字符串；`.get(名字, 默认值)` 只在变量**不存在**时才用默认值，所以发出去的模型名是 `''`。

- 文件：`collector/collect.py`，第 451 行附近
- 原文（行首 4 个空格）：
  ```python
      model = os.environ.get("PS_LLM_MODEL", "deepseek-chat")
  ```
- 改成（行首 4 个空格）：
  ```python
      model = os.environ.get("PS_LLM_MODEL") or "deepseek-chat"
  ```
- 只改这一行。不要改 workflow，不要去建 Variable。
- 验收：
  ```bash
  grep -c -F 'model = os.environ.get("PS_LLM_MODEL") or "deepseek-chat"' collector/collect.py
  grep -c -F 'os.environ.get("PS_LLM_MODEL", "deepseek-chat")' collector/collect.py
  python -X utf8 -c "import ast;ast.parse(open('collector/collect.py',encoding='utf-8').read());print('语法 OK')"
  ```
  三条依次输出 `1`、`0`、`语法 OK`。（第二条 exit 是 1，这是 grep「没有」的意思，正常。）
- check 会给 REVIEW（collector 代码），标题加 `[待审]`。
- 合并之后：手册 §6 写了怎么判断 B01 合没合并、合并后 400 怎么处理。

### [ ] B02 · RESULTS.md 的示例行和真实结果混在一张表里

第一条真实结果加进来以后，「上面两行是格式示例」这句话就错了。

- 文件：`RESULTS.md`
- 原文（第 5–12 行）：
  ~~~markdown
  ## 格式

  | 实验 | 谁 | 结果（一句话） | 日期 | 链接 |
  |---|---|---|---|---|
  | 微波炉测光速 | @someone | d=6.1cm，算出 2.99×10⁸ m/s | 2026-10-20 | [链接](https://github.com/) |
  | LED 估普朗克常数 | @another | 算出 5.4×10⁻³⁴，偏小 20%，原因是万用表内阻 | 2026-10-21 | [链接](https://github.com/) |

  上面两行是格式示例，不是真实数据。
  ~~~
- 改成：
  ~~~markdown
  ## 格式

  每条结果占一行，像这样（这两行只是示例，不是真实数据）：

  ```markdown
  | 微波炉测光速 | @someone | d=6.1cm，算出 2.99×10⁸ m/s | 2026-10-20 | [链接](https://github.com/) |
  | LED 估普朗克常数 | @another | 算出 5.4×10⁻³⁴，偏小 20%，原因是万用表内阻 | 2026-10-21 | [链接](https://github.com/) |
  ```

  ## 结果

  | 实验 | 谁 | 结果（一句话） | 日期 | 链接 |
  |---|---|---|---|---|
  ~~~
- 同一个文件，「## 怎么加」下面那行 `在表格末尾加一行，提 PR。不用漂亮，写清楚三件事：` 改成 `在「结果」表格末尾加一行，提 PR。不用漂亮，写清楚三件事：`
- 验收：
  ```bash
  grep '^## \|^| 实验' RESULTS.md
  ```
  正好输出这 5 行：
  ```
  ## 格式
  ## 结果
  | 实验 | 谁 | 结果（一句话） | 日期 | 链接 |
  ## 怎么加
  ## 更好的分享方式
  ```

### [ ] B03 · 法拉第页「需要」行还写着交流 mV 档

步骤 2 已经改成 DC mV 档并解释了为什么，元信息表没跟上。

- 文件：`experiments/faraday-induction.md`，第 7 行（「需要」那一行）
- 原文：`万用表（交流 mV 档）`（只是这一行里的一段）。改成：`万用表（DC mV 档）`。这一行其他文字不动。
- 验收：
  ```bash
  grep -c -F '交流 mV' experiments/faraday-induction.md
  grep -c -F '万用表（DC mV 档）' experiments/faraday-induction.md
  ```
  两条依次输出 `0`、`1`。
- check 会给 REVIEW（实验页），标题加 `[待审]`。

### [ ] B04 · 微波炉页正文的成功标准和验收对不上

验收写的是 2.4–3.4×10⁸ m/s（相对 3.0×10⁸ 大约 −20% 到 +13%），正文却说 10% 以内算成功。以验收为准。

- 文件：`experiments/microwave-speed-of-light.md`，第 17 行
- 原文：`` `d` 大概会是 6 厘米。不是 6 厘米也没关系，10% 以内都算成功。``
- 改成：`` `d` 大概会是 6 厘米。不是 6 厘米也没关系，c 落在 2.4–3.4×10⁸ m/s 都算成功。``
- 第 42 行 `误差 10% 以内算正常，5% 以内算手稳。` **不要动**（那是质量评价，不是成功标准）。
- 验收：`grep -F '10%' experiments/microwave-speed-of-light.md` 正好输出一行：`误差 10% 以内算正常，5% 以内算手稳。`
- check 会给 REVIEW（实验页），标题加 `[待审]`。

### [ ] B05 · 「从哪开始」把 ¥15 的盲测可乐推给「一分钱不想花」的人

- 文件：`README.md` 第 68 行、`README.en.md` 第 64 行，两处一起改。
- `README.md` 原文：
  ```
  | 一分钱不想花 | [盲测可乐](experiments/blind-cola.md)——先搞清楚自己是不是真喝得出来 | 1 小时 |
  ```
  改成：
  ```
  | 一分钱不想花 | [拍手测声速](experiments/sound-speed.md)——一声拍手一次回声，算出声速 | 20 分钟 |
  ```
- `README.en.md` 原文：
  ```
  | No money at all | [Blind Coke test](experiments/blind-cola.md) — can you actually tell? | 1 hr |
  ```
  改成：
  ```
  | No money at all | [Speed of sound with a clap](experiments/sound-speed.md) — one clap, one echo | 20 min |
  ```
- 下面清单表里的盲测可乐那行**不要动**。
- 验收：
  ```bash
  grep -c -F '| 一分钱不想花 | [拍手测声速](experiments/sound-speed.md)' README.md
  grep -c -F '| No money at all | [Speed of sound with a clap](experiments/sound-speed.md)' README.en.md
  grep -c -F 'blind-cola.md)——先搞清楚自己是不是真喝得出来' README.md
  ```
  三条依次输出 `1`、`1`、`0`。

### [ ] B06 · README 说实验时长「30 分钟起」，其实最短 20 分钟

- `README.md` 第 20 行：把 `30 分钟到 5 天的都有` 改成 `20 分钟到 5 天的都有`。
- `README.en.md` 第 16 行：把 `30 minutes to 5 days` 改成 `20 minutes to 5 days`。
- 验收：
  ```bash
  grep -c -F '20 分钟到 5 天的都有' README.md
  grep -c -F '20 minutes to 5 days' README.en.md
  ```
  两条都输出 `1`。

### [ ] B07 · 中文 README 的点子池比英文少两条

- 文件：`README.md`，「## 点子池」那一节。
- 在 `- 鸡蛋浮沉测盐水密度` 这一行**后面**插入一行：`- 不同品牌食盐溶解速率`
- 在 `- 煮蛋时间与蛋黄凝固状态` 这一行**后面**插入一行：`- 红绿灯等待时间分布`
- 顺序和 `README.en.md` 的 Idea pool 一一对应，改完两边都是 11 条。
- 验收：
  ```bash
  sed -n '/^## 点子池/,/^---/p' README.md | grep -c '^- '
  sed -n '/^## Idea pool/,/^---/p' README.en.md | grep -c '^- '
  ```
  两条都输出 `11`。

### [ ] B08 · 中文贡献指南漏了英文清单、翻译范围也比英文版窄

- 文件：`CONTRIBUTING.md`
- 第 29 行原文：`3. 在 [README.md](README.md) 对应的分类表格里加一行`
  改成：`3. 在 [README.md](README.md) 对应的分类表格里加一行（能的话 [README.en.md](README.en.md) 也加一行）`
- 第 30 行原文：`4. 提 PR`
  改成：`4. 提 PR。会自动跑一个叫 check 的检查；红了多半是清单表格或实验数量没同步，不会改也没关系，维护者会帮你补`
- 第 38 行原文：``- 实验页 → `experiments/<原名>.en.md` ``
  改成：``- 实验页 → `experiments/<原名>.en.md`（从英文翻成中文就用 `.zh.md`）``
- 第 39 行原文：`- 清单和章程 → 直接改 [README.en.md](README.en.md) / [CHARTER.en.md](CHARTER.en.md)`
  改成：`- 清单、章程和宣言 → 直接改 [README.en.md](README.en.md) / [CHARTER.en.md](CHARTER.en.md) / [MANIFESTO.en.md](MANIFESTO.en.md)`
- 验收：
  ```bash
  grep -c -F -e '对应的分类表格里加一行（能的话 [README.en.md](README.en.md) 也加一行）' -e '4. 提 PR。会自动跑一个叫 check 的检查' -e '（从英文翻成中文就用 `.zh.md`）' -e '- 清单、章程和宣言 → 直接改' CONTRIBUTING.md
  ```
  输出 `4`。

### [ ] B09 · 9 份旧草稿的「未核对」标记是 HTML 注释，网页上看不见

新格式草稿的第一行是可见的 `> ⚠️` 引用块；旧格式的第一行是 `<!--` 注释，GitHub 上渲染出来看不到警告。
新旧**以第一行是不是 `<!--` 为准**，不看日期（2026-10-25 的埃拉托色尼那份也是旧格式）。现在旧格式有 9 份。

- 文件：`inbox/designs/` 下以 `<!-- 草稿：` 开头的草稿（2026-10-25 是 9 份，主人删过草稿就会少），外加 `inbox/designs/README.md`。
- 有开着的「删草稿」PR（手册 §2.4 第一条命令列出的、分支名带 `-rm-` 的 `dsh/` PR）时**不做这条**：两个 PR 会动同一批文件。
- 先数旧格式草稿有几份，记下这个数 N：
  ```bash
  grep -l '^<!-- 草稿：' inbox/designs/2026-*.md | wc -l
  ```
  N 是 `0` → 不做这条，日报写「B09 已经没有旧格式草稿」。
- 草稿用下面这段脚本改（只换前两行，内容不动，原文网址原样搬过去；已经是新格式的会跳过）。在仓库根目录整段复制运行：
  ```bash
  python -X utf8 - <<'EOF'
  import pathlib, re
  NEW = "> ⚠️ **AI 草稿，未经人工核对。** 型号、价格、参数待核实；改完才能进 `experiments/`。"
  for p in sorted(pathlib.Path("inbox/designs").glob("2026-*.md")):
      lines = p.read_bytes().decode("utf-8").split("\n")
      m = re.fullmatch(r"<!-- 草稿：AI 生成，未经人工核对。原文：(\S+) -->", lines[0])
      if not m or not lines[1].startswith("<!-- 待核实"):
          continue
      lines[0] = NEW
      lines[1] = "> 原文：" + m.group(1)
      p.write_bytes("\n".join(lines).encode("utf-8"))
      print("改了", p.name)
  EOF
  ```
  应该打印 N 行「改了 …」。
- `inbox/designs/README.md` 第 6–7 行（在一个 ```` ``` ```` 代码块里面，代码块的开头结尾两行不动）原文：
  ```
  <!-- 草稿：AI 生成，未经人工核对。原文：... -->
  <!-- 待核实：型号、价格、参数请对照原文确认后再进 experiments/ -->
  ```
  改成：
  ```
  > ⚠️ **AI 草稿，未经人工核对。** 型号、价格、参数待核实；改完才能进 `experiments/`。
  > 原文：...
  ```
- 验收：
  ```bash
  grep -L '^> ⚠️' inbox/designs/2026-*.md
  grep -c -F '<!-- 草稿：' inbox/designs/README.md
  git -c core.quotepath=false diff --stat
  ```
  验收在 `git add` 之前跑（手册 §3.7 第 2 步就是这个顺序；add 之后第三条就没有输出了）。
  第一条没有输出；第二条输出 `0`；第三条列出改了的 N 份草稿和 `inbox/designs/README.md`，每个文件后面都是 `| 4 ++--`，
  最后一行是 ` <N+1> files changed, <2×(N+1)> insertions(+), <2×(N+1)> deletions(-)`。
  N 是 9 时就是 ` 10 files changed, 20 insertions(+), 20 deletions(-)`。
- **不要动 `inbox/designed.json`。** 提交时 `git add` 逐个写文件名（文件名有中文，用引号包起来）。
- check 会给 REVIEW（改了草稿），标题加 `[待审]`。

### [ ] B10 · collector/README 有四处和代码对不上

- 文件：`collector/README.md`
- 第 31 行原文：
  ```
  | `inbox/triaged.json` | 已经筛过的 id，下次不再重复送进模型 |
  ```
  改成：
  ```
  | `inbox/triaged.json` | 被 AI 选进「可以直接写成实验页」的 id，下次不再送进模型（没选中的仍会重复送审） |
  ```
- 第 50 行原文：`读 inbox/raw.json，按这四条判断每一条：`
  改成：`读 inbox/pool.json，按这四条判断每一条：`
  （只换文件名。「四条」对不对是另一个问题，在 🧠 区，不要动。）
- 第 76 行原文：`目前支持三类，照着抄就行：`
  改成：`目前支持五类，照着抄就行：`
- 第 118 行原文：
  ```
  - 池子有 150 条上限；另外 `triaged.json` 保证"已经筛过的不再重复送进模型"，避免经典种子库每天被选同一批。
  ```
  改成：
  ```
  - 池子有 150 条上限；另外 `triaged.json` 记下被 AI 选中过的条目，不再重复送进模型，避免经典种子库每天被选同一批。
  ```
- 验收：`grep -n '已经筛过的\|读 inbox/raw.json\|三类' collector/README.md` 没有输出。
- check 会给 REVIEW（collector 目录），标题加 `[待审]`。

### [ ] B11 · collect.py 里两段说明文字过时

- 文件：`collector/collect.py`
- 第 524 行原文（行首 4 个空格）：
  ```python
      """14 天滚动池。每天的 raw 只有当天新增，AI 看到的太少；池子才是它的输入。"""
  ```
  改成：
  ```python
      """30 天滚动池（经典/维基条目不过期，上限 150 条）。每天的 raw 只有当天新增，AI 看到的太少；池子才是它的输入。"""
  ```
- 第 553 行原文（行首 8 个空格）：
  ```python
          "完整原始池在 [raw.json](raw.json)。挑出来的写进 `inbox/candidates.md`，",
  ```
  改成：
  ```python
          "今天新增的在 [raw.json](raw.json)，完整滚动池在 [pool.json](pool.json)。挑出来的写进 `inbox/candidates.md`，",
  ```
- 只改引号里的文字，引号、逗号、缩进都不动。
- 验收：
  ```bash
  grep -n '14 天\|完整原始池' collector/collect.py
  python -X utf8 -c "import ast;ast.parse(open('collector/collect.py',encoding='utf-8').read());print('语法 OK')"
  ```
  第一条没有输出，第二条输出 `语法 OK`。
- check 会给 REVIEW，标题加 `[待审]`。B01、B16 也改 `collect.py`，但改的是别的行，git 能自动合并，不用等它们。

### [ ] B12 · triage.py 开头的说明还停在只读 raw.json 的时候

- 文件：`collector/triage.py`，第 3 行
- 原文：
  ```python
  """AI 筛选：把 inbox/raw.json 变成人可以直接看的 inbox/candidates.md
  ```
  改成：
  ```python
  """AI 筛选：读 inbox/pool.json（没有才用 raw.json），写 inbox/candidates.md 和 picked.json，选中的 id 记进 triaged.json
  ```
- 行首的三个双引号保留，这一行末尾不要加引号。
- 验收：
  ```bash
  grep -c -F '"""AI 筛选：读 inbox/pool.json（没有才用 raw.json），写 inbox/candidates.md 和 picked.json，选中的 id 记进 triaged.json' collector/triage.py
  python -X utf8 -c "import ast;ast.parse(open('collector/triage.py',encoding='utf-8').read());print('语法 OK')"
  ```
  两条依次输出 `1`、`语法 OK`。
- check 会给 REVIEW，标题加 `[待审]`。

### [ ] B13 · deploy/README 的几处过时说明

- 文件：`deploy/README.md`
- 第 31 行：`## 三个上站方案` 改成 `## 四个上站方案`（下面确实有 A、B、C、D 四个）。
- 第 105 行：`3. （可选）启用 AI 推荐理由：` 改成 `3. （可选）启用 AI（推荐理由、AI 筛选、AI 设计草稿）：`
- 第 110–114 行原文：
  ```
  产物会直接提交回仓库：

  - `inbox/raw.json` — 今天的原始池
  - `inbox/prefilter.md` — 机器排序
  - `feed/latest.json` / `latest.js` — 网页看板数据
  ```
  改成：
  ```
  产物会直接提交回仓库，完整清单见 [collector/README.md](../collector/README.md) 的「产出」表。
  ```
- 第 127 行（` ```cron ` 代码块里唯一那一行）整行替换。原文：
  ```
  17 22 * * * cd /srv/personal-science && git pull -q && /usr/bin/python3 collector/collect.py >> /var/log/ps-collect.log 2>&1 && git add -A inbox feed collector/seen.json && git commit -qm "collect: $(date -u +%F)" && git push -q
  ```
  改成：
  ```
  17 22 * * * cd /srv/personal-science && git pull -q && /usr/bin/python3 collector/collect.py >> /var/log/ps-collect.log 2>&1 && /usr/bin/python3 collector/triage.py >> /var/log/ps-collect.log 2>&1 && /usr/bin/python3 collector/design.py --top 2 >> /var/log/ps-collect.log 2>&1; git add -A inbox feed collector/seen.json && git commit -qm "collect: $(date -u +\%F)" && git push -q
  ```
  （给 Claude 的说明，DSH 照抄即可：crontab 里没转义的 `%` 会被当成换行，原来那行的提交永远失败，所以要写 `\%`；
  `;` 让 AI 步骤失败时照样提交采集结果，和 GitHub Actions 上 `if: !cancelled()` 的行为一致。）
- 在下面这一行（第 130 行）后面插入两行：一个空行，和再下面代码块里那一行。原文（整行）：
  ```
  注意：服务器时区一般是 UTC；用 deploy key 才能 push；日志在 `/var/log/ps-collect.log`。
  ```
  要插入的那一行：
  ```
  AI 筛选和草稿要用 `PS_LLM_KEY`：cron 不读 `~/.bashrc`，要在 crontab 最上面单独写一行 `PS_LLM_KEY=你的 key`。不配也能跑，triage 和 design 会自动跳过。命令里的 `\%` 是故意的：crontab 里不转义的 `%` 会把命令截断。
  ```
- 「定时任务的三条纪律」第 3 条里的 `90 条` 改成 `120 条`。
- 改动从下往上做（先改 136 行附近，最后改 31 行），行号就不会错位。
- 验收：
  ```bash
  grep -n '三个上站\|90 条\|启用 AI 推荐理由\|+%F' deploy/README.md
  grep -c 'design.py --top 2 >> /var/log/ps-collect.log 2>&1; git add' deploy/README.md
  python -X utf8 maintenance/check.py | tail -1
  ```
  第一条没有输出；第二条输出 `1`；第三条以 `check: 0 error,` 开头。

### [ ] B14 · README 说「任何 OpenAI 兼容接口都行」，只配 key 其实不够

- `README.md` 第 163 行原文（做过 B07 之后是第 165 行，以原文为准）：
  ```
  > 想启用 AI 筛选和 AI 设计草稿，需要配一个 `PS_LLM_KEY`（任何 OpenAI 兼容接口都行）。没配也不影响采集和提交。
  ```
  改成：
  ```
  > 想启用 AI 筛选和 AI 设计草稿，需要配一个 `PS_LLM_KEY`（默认用 DeepSeek；换别的 OpenAI 兼容接口，还要在仓库 Variables 里配 `PS_LLM_BASE` 和 `PS_LLM_MODEL`，见 [deploy/README.md](deploy/README.md)）。没配也不影响采集和提交。
  ```
- `README.en.md` 第 164 行原文（做过 B15 之后是第 166 行，以原文为准）：
  ```
  > To enable AI filtering and AI-designed drafts, set a `PS_LLM_KEY` (any OpenAI-compatible endpoint works). Without it, collection and commits still run.
  ```
  改成：
  ```
  > To enable AI filtering and AI-designed drafts, set a `PS_LLM_KEY` (DeepSeek by default; for another OpenAI-compatible endpoint, also set the `PS_LLM_BASE` and `PS_LLM_MODEL` repository variables — see [deploy/README.md](deploy/README.md), in Chinese). Without it, collection and commits still run.
  ```
- 验收：`grep -n 'any OpenAI-compatible endpoint works\|任何 OpenAI 兼容接口都行' README.md README.en.md` 没有输出。

### [ ] B15 · 贡献指南缺中英切换，英文 README 缺 CI 徽章

- `CONTRIBUTING.md`：在 `# 怎么加一个实验` 这一行（第 1 行）后面插入两行：一个空行，和 `**中文** · [English](CONTRIBUTING.en.md)`。
- `CONTRIBUTING.en.md`：在 `# How to add an experiment` 这一行（第 1 行）后面插入两行：一个空行，和 `**English** · [中文](CONTRIBUTING.md)`。
- `README.en.md`：在以 `[中文](README.md) · [One-minute version]` 开头的那一行（第 10 行）**前面**插入两行：
  徽章行，和一个空行。徽章行是 `README.md` 里以 `[![collect](` 开头的那一整行（`grep -F '[![collect](' README.md` 能看到，
  应该正好一行），整行原样复制。
- 验收：
  ```bash
  head -5 CONTRIBUTING.md
  head -5 CONTRIBUTING.en.md
  python -X utf8 -c "e=open('README.en.md',encoding='utf-8').read().split('\n');z=open('README.md',encoding='utf-8').read().split('\n');print(e[8]=='', e[9]==z[11], e[9].startswith('[![collect]('), e[10]=='', e[11].startswith('[中文](README.md)'))"
  python -X utf8 maintenance/check.py | tail -1
  ```
  第一条输出这 5 行（第 2、4 行是空行）：
  ```
  # 怎么加一个实验

  **中文** · [English](CONTRIBUTING.en.md)

  只有三条要求。它们不是随便定的，是[章程](CHARTER.md)第四、五、六条的落地。
  ```
  第二条输出这 5 行（第 2、4 行是空行）：
  ```
  # How to add an experiment

  **English** · [中文](CONTRIBUTING.md)

  Three requirements. They aren't arbitrary — they are [Article 4, 5, and 6 of the charter](CHARTER.en.md), put into practice.
  ```
  第三条输出 `True True True True True`；第四条以 `check: 0 error,` 开头。
- `CHARTER.en.md` 也缺语言切换，但章程归主人管，在 👤 区，不要改。

### [ ] B16 · 推荐理由里关键词会重复（「命中 sensor、camera、sensor」）

- 文件：`collector/collect.py`，第 427 行附近
- 原文（行首 4 个空格）：
  ```python
      item["hits"] = (objs + pers + modern)[:3]
  ```
  改成：
  ```python
      item["hits"] = list(dict.fromkeys(objs + pers + modern))[:3]
  ```
- `hits` 只用来拼显示文字（第 437–438 行），不影响打分。
- 验收：
  ```bash
  grep -c -F 'item["hits"] = list(dict.fromkeys(objs + pers + modern))[:3]' collector/collect.py
  python -X utf8 -c "import ast;ast.parse(open('collector/collect.py',encoding='utf-8').read());print('语法 OK')"
  ```
  两条依次输出 `1`、`语法 OK`。
- check 会给 REVIEW，标题加 `[待审]`。B01、B11 也改 `collect.py`，但改的是别的行，git 能自动合并，不用等它们。

---

## 🧠 交给 Claude

按优先级排。编号是评审里的原始编号，方便回查。

### 实验页：会让人做不成或有安全问题的（先做）

- [ ] **exp-5** `experiments/polarization-tape.md:30` 让用「第二块手机屏幕」当检偏器。手机屏幕不透光，这一步做不了。
- [ ] **exp-4** `experiments/led-planck.md:24` 电路是串联变阻器，做不到「从 0 升压」；阻值调到 0 时 LED 没有限流。
- [ ] **exp-2** `experiments/blind-cola.md:39` 把 p=5.5% 写成「低于」5% 显著性线。
- [ ] **exp-3** `experiments/young-double-slit.md:7,104,111` 称 <5mW 激光「安全」；没要求 Class 2（≤1 mW），鼓励换绿/蓝激光笔却没提功率和绿光笔漏红外。
- [ ] **experiments-m1** `experiments/battery-internal-resistance.md:47` 让用 mV 档测约 1.5 V 的电池，超量程。
- [ ] **exp-24** `experiments/newton-prism.md:64` 安全段提了激光没提太阳；「坑」里推荐验收不认的 LED 光源。

### 实验页：物理说法错了的

- [ ] **exp-9 ~ exp-13** `experiments/eratosthenes.md`（第 26、46、47、52、53 行）五处：同经度看正午时刻差（应为零）、一个月影长画 8 字形、折射 0.5°（夸大几十倍）、要求大圆距离（经度不同时高估 R，应用南北向距离）、影子方向相反时 Δθ 要相加。建议一次改完。
- [ ] **exp-14** `experiments/oersted-magnetism.md:53` 「通电太久磁针会被磁化偏掉」不成立。
- [ ] **exp-15** `experiments/tds-water.md:45` 「用纯净水校准」和本页自己的数据表矛盾。
- [ ] **exp-16** `experiments/galileo-inclined-plane.md:7` 允许用晾衣杆当斜面；球在杆的槽里或两根杆搭成的双轨上滚时，接触半径变小，加速度明显低于 5/7·g·sinθ，验收会不过。
- [ ] **exp-17** `experiments/young-double-slit.md:7` 光栅当双缝平替，没给光栅公式，小角近似会超出验收。
- [ ] **exp-19** `experiments/seed-germination.md:17,29,33` 「绿豆嫌光、见光发芽率 55%」没有来源，很可能不对。
- [ ] **exp-20** `experiments/plant-phototropism.md:38` 建议盒内补光，破坏「唯一光源」；手机放哪也没写清。
- [ ] **exp-25** `experiments/sound-speed.md:47` 「两个手机测单向传播时间」方法不完整（没说怎么对时）。
- [ ] **doc-21** `README.md:102` 杨氏双缝一句话把头发当主路线；英文版说头发能看到「干涉」（实际是衍射）。

### 实验页：不合规范的

- [ ] **exp-18** `experiments/fridge-thermal.md:11` 和 `seed-germination.md` 的「验收」判不了成败，违反 CONTRIBUTING 第 2 条。
- [ ] **exp-6 / doc-8** 17 页里 12 页缺模板规定不能省的「AI 可以怎么帮你」一节（check 里是 WARN，基线记着）。补一页，就从 `maintenance/check_baseline.json` 删掉对应条目。CONTRIBUTING 也要提这一节。
- [ ] **exp-26** 3 页用自定义段名代替「算一下 / 会看到什么」，棱镜页没有预期数值。

### 流水线：会丢数据或静默出错的

- [ ] **ci-2 / ops-m1** `.github/workflows/collect.yml:19,68` 推送重试遇到 rebase 冲突无法恢复；排队的第二个 run 用触发时的旧 SHA，推送必然冲突，整次产出丢失。考虑 checkout 时用 `ref: main`，冲突时重新生成再提交。
- [ ] **pip-5** `collector/triage.py:103` `max_tokens=2400` 会截断，不检查 `finish_reason`，截断的 candidates.md 直接发布。
- [ ] **pip-12** `collector/collect.py:596` 所有网络源都失败时仍 exit 0，CI 是绿的。至少要让 DSH 的日志检查能抓到（现在靠「本轮抓到」数字）。
- [ ] **pip-11** `collector/collect.py:618` 同一天手动重跑会清空当天看板和 raw.json。
- [ ] **pip-17 / ci-3 / doc-11** `inbox/.ai-error` 被 CI 提交，成功后从不删除，文档没写。
- [ ] **pip-9 / ci-5** `collector/collect.py:639` seen.json 只记首次见到的日期且不刷新，120 天后同一批经典/维基条目会被当新内容整批回来。**最早约 2027-02 触发**，在那之前要修。

### 流水线：筛选质量

- [ ] **pip-3** `collector/collect.py:373` 维基搜索结果被标成 targeted，绕过关键词闸门，跑题条目（朝鲜战争、大学、军校）进了公开看板。
- [ ] **pip-13 / ci-8** `collector/collect.py:41` en.wikipedia 在 CI 上每次 4 个查询 429（本机同样请求 200）。查 User-Agent 和请求频率。
- [ ] **collector-m1** `collector/triage.py:151` 每天把几乎同一批被拒条目重新送审，分数低于约 76 的新内容永远到不了模型。和 triaged.json 语义一起定（下一条）。
- [ ] **ci-10 / pip-8 / ci-6** triaged.json 只记选中项；选中超过 `--top 2` 的多余条目被标成已筛、永远不会被设计。要定：triaged 记什么、多出来的怎么办。改完同步 `collector/README.md:31,118`（B10 写的是当前行为）。
- [ ] **pip-14** `collector/collect.py:536` timeless 条目永不过期，跑题维基条目每天在加，会慢慢挤掉新闻源。
- [ ] **pip-10** `collector/triage.py:143` triage 和 design 不知道 `experiments/` 里已有哪些页，反复选中已发布的经典实验（10 份草稿里 6 份重复）。
- [ ] **pip-6 / pip-7** `collector/triage.py:183,185` 只信候选索引不核对标题；靠字符串 `## 需要补设备` 切章节。
- [ ] **pip-18** `collector/triage.py:54,83` candidates.md 头部写「从 144 条里筛」，模型只看到前 40 条；prompt 里索引范围 `从 0 到 {kept_count}` 多了 1。改 prompt 属于改 AI 行为，所以放这里。
- [ ] **pip-21** `collector/triage.py:54` prompt 说判断标准「见章程第四条」，第四条讲的不是筛选标准。
- [ ] **doc-3** `collector/triage.py:44` 危险清单没覆盖章程第五条（活体、需要许可证）；经典种子库里巴甫洛夫那条主动提议拿宠物做训练。
- [ ] **doc-13** `collector/README.md:47-60` 手动筛选 prompt 和自动 triage 不一致：四条还是五条、把「激光」一律排除。
- [ ] **pip-2 / ci-7** design 在 triage 选出 0 条时回退到 pool。主人说过是有意的取舍（commit 253f1e2），**改不改主人定**；Claude 要做的是评估回退时会不会给新闻、播客、危险项写草稿，把证据交给主人。

### 判据（check.py / check.yml）：已知没覆盖的

2026-10-25 加固 check.py 时留下的，都不急，按需要再做。

- [ ] **chk-1** 历史密钥扫描看不到 git 当成二进制的改动：UTF-16 文件里放密钥、提交后再删掉，`--base` 扫不到（工作区里的 UTF-16 文件能扫到）。
- [ ] **chk-2** check.py 把文件名原样打印到 Actions 日志；文件名里带换行时，下一行可以以 `::` 开头被 runner 当成工作流命令。实际意义不大（能开 PR 的人本来就能改 check.yml，见 👤 区），要防可以在外面包一层 `::stop-commands::`。
- [ ] **chk-3** check.yml 只在本地用 bash 模拟过，还没在真 GitHub Actions 上跑过。第一个 PR 开出来时看一眼 Summary 页里有没有「这次改动需要」那一段。
- [ ] **chk-4** 「页面已不在，可从 baseline 删掉」在 `--base` 下仍然只是 INFO，没有像「已补齐」那样升成 ERROR。

### 文档

- [ ] **doc-9** `SKILL.md:14` 单独交给 AI 时拿不到清单：只有一个相对链接，没有实验列表和仓库网址。
- [ ] 看板 `feed/index.html` 显示 AI 推荐理由（`why` 字段）之前，确认 B01 合并后理由的质量。

---

## 👤 交给主人

- [ ] **提交 `.gitignore`**（最急）。它是唯一挡住本地 `.tmp/` 被误提交的规则，现在没进版本库。一起提交的还有 `AGENTS.md`、`CLAUDE.md`、`maintenance/`、`.github/workflows/check.yml`，以及 `README.md`、`README.en.md`（仓库结构那一节）。提交时按路径 add，不要 `git add -A`。
- [ ] **check 挡不住改流水线本身的 PR**：PR 上的 check 用的是 main 上那一版 check.py，但 workflow 文件 `.github/workflows/check.yml` 用的是 PR 里的那一份——PR 改了它，就能让 check 变绿。合并前看一眼 PR 的文件列表：动了 `.github/`、`maintenance/`、`collector/`、`AGENTS.md`、`CLAUDE.md` 的，只合 Claude 审过的；再看一眼来源仓库是不是本仓库（fork 来的 PR 分支名也可以叫 `dsh/…`）。
- [ ] **DSH 用的是你的 gh 账号**：文档只能约束它，技术上它能做你能做的一切（合并、改设置）。要更稳，给 DSH 单独一个 fine-grained token，只给本仓库 Contents 和 Pull requests 的读写，不给 Administration、Secrets、Workflows。
- [ ] **（可选）本机 pre-push 钩子**：在 `.git/hooks/pre-push` 里拒绝推 `main`，防 DSH 误推。这是本机设置，不进仓库；你自己要直推 main 时用 `git push --no-verify`。
- [ ] **main 分支保护**：现在允许 force-push 和删除。建议加一条 ruleset：禁止 force-push、禁止删除。**不要**要求 PR 才能推送——机器人每天直接推 main。
- [ ] **design 回退到 pool**（pip-2 / ci-7）：保留还是去掉。Claude 会先把证据整理好。
- [ ] **LICENSE**（doc-10）：现在不是标准 CC0 文本，GitHub 识别成 Other；代码部分的许可也没写清。
- [ ] **idea 标签**（doc-22）：`.github/ISSUE_TEMPLATE/experiment-idea.md` 用的 `idea` 标签在仓库里不存在。建一个，或者从模板里删掉。
- [ ] **看板部署**（ci-11）：`feed/index.html` 没部署，README 指过去在 GitHub 上只能看到源码。选 `deploy/README.md` 里的哪个方案。
- [ ] **草稿保留策略**（ci-13）：`inbox/designs/` 只增不减。要不要定期清理、清理时谁来做。
- [ ] **空的 GitHub Environment「111」**：仓库 Settings → Environments 里有一个叫 111 的空环境，看着像误建。
- [ ] **章程两处文字**：`CHARTER.md:89`「它不意思是」→「它不意味着」；`CHARTER.md:79` 第五条要不要写成「化学品入口或吸入」；`CHARTER.en.md` 缺 `**English** · [中文](CHARTER.md)` 切换行。主人同意后可以写成 🟢 条目交给 DSH。
- [ ] **DSH 能不能在 issue / PR 下评论**：现在规定一律不评论、只写草稿。要放开就改 `AGENTS.md` 红线第 7 条。

---

## 已经核对过、不用改的

这些在评审里被怀疑过，复核后确认没问题。看到了不要再报。

- 17 页实验的核心公式和数值（微波炉 `d × 4.9×10⁷`、g、声速、电池内阻等）复核无误。上面 🧠 区列出的是全部问题。
- 每页元信息表和 README 清单表的时间、花费、难度一致。
- `archive/` 里的占位链接是故意的，check 不查 `archive/`。
- `designed.json` 比草稿多 2 个 id：主人删掉的米尔格拉姆服从实验和车载摄像头那篇，id 故意留着防止重新生成。
- 每次定时运行都有一个 ps-bot 提交：时间戳每次都变，是正常的。
- design 回退到 pool 是主人有意的设计（是否保留见 👤 区），不是 bug。
