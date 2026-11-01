# 自动转正审计日志

`collector/promote.py` 每次真正发布都会在这里追加一行；**完整的证据链（来源、策展理由、风险评审全文）在对应 PR 的正文里**。

规则：每天最多 1 篇、7 天最多 3 篇；只有 `risk_level=low` + `verdict=approve` + check 全绿才自动合并。

| 日期 | 标题 | slug | 策展分 | 风险 | PR |
|---|---|---|---|---|---|
| 2026-11-01 | 光电效应（用 LED 反做）：用几块钱的 LED 测出普朗克常数 | measuring-planck-s-constant-with-leds | 9 | high | https://github.com/dongsheng123132/personal-science/pull/2 |
