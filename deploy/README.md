# 放哪跑

## 推荐：GitHub Actions（免费，机器在美国）

`.github/workflows/collect.yml` 已经写好了，默认每天跑一次。

**为什么不用自己租服务器**：GitHub 的 runner 本身就在美国，每天一次任务免费额度绰绰有余，还不用管系统更新、证书、磁盘。你要的"定期、在美国、跑采集"，它天生就是。

配置：

1. 推到 GitHub
2. 仓库 Settings → Actions → General，确认 workflow 有写权限
3. （可选）想启用 AI 推荐理由：
   - Settings → Secrets and variables → Actions
   - Secret 加 `PS_LLM_KEY`（DeepSeek 的 key）
   - Variable 加 `PS_LLM_BASE` = `https://api.deepseek.com`，`PS_LLM_MODEL` = `deepseek-chat`
4. 想立刻跑一次：Actions → collect → Run workflow

产物会直接提交回仓库：

- `inbox/raw.json` — 今天的原始池
- `inbox/prefilter.md` — 机器排序
- `feed/latest.json` / `latest.js` — 网页看板数据

## 备选：自己的美国 VPS

如果哪天要跑得很重（比如加几十个源、每小时一次），再上 VPS。

```bash
# 1. 拉仓库
git clone https://github.com/<you>/personal-science /srv/personal-science
cd /srv/personal-science

# 2. 先手动跑一次确认
python3 collector/collect.py

# 3. 加 cron（每天 UTC 22:17）
crontab -e
```

```cron
17 22 * * * cd /srv/personal-science && git pull -q && /usr/bin/python3 collector/collect.py >> /var/log/ps-collect.log 2>&1 && git add -A inbox feed collector/seen.json && git commit -qm "collect: $(date -u +%F)" && git push -q
```

注意：

- 服务器时区通常是 UTC，cron 写 UTC 时间
- 机器要能 git push，用 deploy key
- 日志在 `/var/log/ps-collect.log`

## 定时任务的三条纪律

1. **失败不能静默。** 脚本里每个源都单独 try，一个源挂了不影响别的；但真的全挂了，日志要能看出来。
2. **空跑要正常。** 今天没有新东西就提交空内容或不提交，别报错。
3. **去重库要跟着走。** `collector/seen.json` 必须一起提交，不然每天都会看到同样 90 条。

## 网页看板

`feed/index.html` 是纯静态的，读 `feed/latest.js`。

- 想公开：仓库 Settings → Pages → 分支选 `main`、目录选 `/feed`
- 不想公开：本地双击 `feed/index.html` 也能看（不需要服务器）

## 一句话

**GitHub Actions = 美国机器 + 免费 + 不用运维。先用它，等真需要了再租机器。**
