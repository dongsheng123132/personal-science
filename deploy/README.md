# 放哪跑、放哪看

## 一句话结论

| 东西 | 放哪 | 为什么 |
|---|---|---|
| 清单、实验页、章程 | **GitHub 仓库** | 内容就该在能 PR 的地方，别搬 |
| 每天采集 | **GitHub Actions** | 它本来就是美国机器，每天一次免费 |
| 网页看板 | **Cloudflare Pages 或 Vercel** + 自定义域名 | 静态站，零运维，自动跟仓库更新 |
| 美国服务器 | **现在不要** | 静态站用不上，国内还慢，多一份运维 |

**"放到美国服务器"这件事，GitHub Actions 已经替你做完了。**

---

## 为什么不上美国服务器

1. **内容是静态的。** 一个清单 + 每天一份 JSON，不需要后端、不需要数据库。静态站放服务器是浪费。
2. **美国 VPS 对国内更慢。** 没有优化线路的话，从深圳访问美国 VPS 经常还不如 Vercel 的 CDN。
3. **运维是负债。** 系统更新、证书续期、磁盘满、被扫、被墙——这些时间都该拿去做实验。
4. **你已经有"美国机器"了。** Actions 的 runner 在美国，免费额度对每天一次任务绰绰有余。

什么时候才值得租服务器：

- 要跑长任务（视频下载/转录、批量抓图）
- 要 API、上传、数据库（比如以后让别人提交实验记录）
- 要国内加速 —— 那时候也不是美国服务器，是**备案 + 国内 CDN**

---

## 三个上站方案

### A. 先不上网站（最省事）

- 看板：本地双击 `feed/index.html` 就能看
- 每日候选：直接看 GitHub 上的 [`inbox/candidates.md`](../inbox/candidates.md)
- 清单：GitHub 渲染 `README.md` 就是网页

适合"先跑两周再说"。**这也是我建议的起点。**

### B. Cloudflare Pages（推荐，如果你域名的 DNS 在 Cloudflare）

1. 仓库推到 GitHub
2. Cloudflare Dashboard → Workers & Pages → Create → Pages → Connect to Git
3. 选仓库；**Build command 留空**，**Build output directory 填 `feed`**
4. 部署成功后 → Custom domain → 绑一个子域（比如 `ps.hequbing.com`）
5. 以后 collect workflow 一提交，Cloudflare 自动重新部署

优点：免费、自动部署、全球 CDN、国内访问比 Vercel 裸域稳一点。

### C. Vercel

1. Import 仓库
2. Framework Preset 选 **Other**；**Root Directory 填 `feed`**；Build Command 留空
3. Deploy → 绑自定义域名

优点：上手最快。缺点：`*.vercel.app` 裸域在国内经常不稳，**一定要绑自己的域名**。

### D. GitHub Pages（只适合海外读者）

Pages 设置里只能选仓库根目录或 `/docs`，选了 `/feed` 不行，要用 workflow：

```yaml
name: pages
on:
  push:
    branches: [main]
permissions:
  pages: write
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: github-pages
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: feed
      - uses: actions/deploy-pages@v4
```

**但 `*.github.io` 在国内经常打不开。** 如果读者是普通人，别拿它当入口。

---

## 域名的两个坑

1. **海外托管（Vercel / Cloudflare Pages）不需要备案。** 绑了域名直接能用。
2. **想用国内 CDN 提速才需要备案**，而且是"域名 + 接入商"一起备案，不能用别的域名的备案号顶替。

所以路径是：先用海外托管 + 自定义域名跑起来；真的需要国内速度了，再去备案、换国内 CDN。

---

## 每天采集放哪跑：GitHub Actions（已配好）

`.github/workflows/collect.yml` 默认每天 UTC 22:17（北京 06:17）跑一次。

配置：

1. 推到 GitHub
2. 仓库 Settings → Actions → General，确认 workflow 有写权限
3. （可选）启用 AI 推荐理由：
   - Secret 加 `PS_LLM_KEY`（DeepSeek 的 key）
   - Variable 加 `PS_LLM_BASE` = `https://api.deepseek.com`，`PS_LLM_MODEL` = `deepseek-chat`
4. 想立刻跑一次：Actions → collect → Run workflow

产物会直接提交回仓库：

- `inbox/raw.json` — 今天的原始池
- `inbox/prefilter.md` — 机器排序
- `feed/latest.json` / `latest.js` — 网页看板数据

## 备选：自己的 VPS

哪天要跑得很重（几十个源、每小时一次）再上。

```bash
git clone https://github.com/<you>/personal-science /srv/personal-science
cd /srv/personal-science && python3 collector/collect.py
crontab -e
```

```cron
17 22 * * * cd /srv/personal-science && git pull -q && /usr/bin/python3 collector/collect.py >> /var/log/ps-collect.log 2>&1 && git add -A inbox feed collector/seen.json && git commit -qm "collect: $(date -u +%F)" && git push -q
```

注意：服务器时区一般是 UTC；用 deploy key 才能 push；日志在 `/var/log/ps-collect.log`。

## 定时任务的三条纪律

1. **失败不能静默。** 每个源单独 try，一个挂了不影响别的；但全挂了要能从日志看出来。
2. **空跑要正常。** 今天没有新东西就提交空内容或不提交，别报错。
3. **去重库要跟着走。** `collector/seen.json` 必须一起提交，不然每天都是同样的 90 条。

## 一句话

**内容留在 GitHub，任务交给 Actions，看板挂 CDN，服务器能不租就不租。**
