# AI 自动赚钱机器 (AI Earning Machine)

每天自动运行的「内容 + 数字产品」变现系统：Claude 选题 → 写 SEO 长文 → 生成付费手册 → 生成带变现位的网站 → 部署到 GitHub Pages → 拉取 Stripe 真实收入。

```
GitHub Actions（每天 06:17 UTC）
  └─ python -m earnbot run
       1. plan_topics     选长尾关键词（去重，覆盖多个细分赛道）
       2. write_article   写 1500–2200 字文章（结构化 JSON，只能推荐 config 里的联盟产品）
       3. create_product  生成付费手册：公开销售页 + 私密完整版（deliverables/，不进公开仓库）
       4. site.build      静态站：首页 / 文章 / 产品页 / sitemap / RSS / robots / JSON-LD
       5. revenue         读取 Stripe 近 30 天收入 → data/revenue.json
  └─ 提交新内容 → 部署 GitHub Pages
```

## 四条收入渠道

| 渠道 | 怎么赚钱 | 你需要做的（一次性） |
|---|---|---|
| 联盟佣金 | 文章里的工具推荐链接 | 注册各工具的联盟计划，把带追踪码的链接填进 `config.toml` 的 `[[affiliates]]` |
| 自有数字产品 | 每份手册约 $19 | 在 Stripe 建 Payment Link（或上架 Gumroad），把 `产品slug = "链接"` 填进 `[checkout]`；完整手册从 Actions 的 artifact 下载后作为交付文件上传 |
| 广告 | 流量够后接 AdSense | 审核通过后填 `adsense_client` |
| 邮件列表 | 长期复购的核心资产 | Buttondown/Beehiiv 等的表单地址填 `newsletter.form_action` |

## 启动步骤（约 30 分钟，这几步只有你能做——需要你本人的账户和身份）

1. **GitHub Secrets**（Settings → Secrets and variables → Actions）：
   - `ANTHROPIC_API_KEY`（必需，来自 console.anthropic.com）
   - `STRIPE_API_KEY`（可选，建议用只读 restricted key，用于收入统计）
2. **开启 Pages**：Settings → Pages → Source 选 **GitHub Actions**。
3. **合并到 `main`**，然后在 Actions 里手动运行一次 `autopilot`。
4. 把网站提交到 **Google Search Console**（提交 `sitemap.xml`）——不做这步搜索引擎发现会慢很多。
5. 填联盟链接和 Stripe 链接（见上表）。没填之前网站照样运行，只是对应位置显示「即将上线」。

本地运行：`pip install -r requirements-dev.txt && python -m pytest && python -m earnbot run && python -m earnbot status`

## 成本

默认每天 2 篇文章 + 最多 1 份产品（总量上限 12 份），模型 `claude-opus-5-5`。每天 API 费用大约几美元以内；嫌贵可在 `config.toml` 把 `effort` 改成 `medium`，或减少 `articles_per_run`。GitHub Pages 托管免费。

## 实话：会不会有人买？没人买怎么办？

- **文章本身不卖钱**，它的作用是带来搜索流量；钱来自流量里一小部分人点联盟链接、买手册、订阅邮件。
- **新站通常要 3–6 个月以上**才开始有稳定的搜索流量，前几个月收入接近 0 是常态，不是故障。
- 很多纯 AI 批量内容站最终赚不到钱：搜索引擎会打压「规模化低质内容」。所以本系统刻意限量（每天 2 篇）、禁止编造数据、只推荐真实适合的产品、带联盟披露。
- 判断标准（用 `python -m earnbot status` + Search Console 看）：

| 时间 | 健康信号 | 不达标怎么做 |
|---|---|---|
| 第 1 个月 | 页面被收录 | 检查 sitemap 是否提交、Pages 是否正常 |
| 第 3 个月 | 每天有自然搜索点击 | 换更细分的 `niches`，改中文 / 其他语言市场 |
| 第 6 个月 | 有第一笔联盟佣金或产品销售 | 把流量最高的文章对应的主题做成产品；砍掉没流量的赛道 |
| 之后 | 邮件订阅持续增长 | 邮件列表是最可控的资产，优先做 |

调整方向只需要改 `config.toml`（赛道、语言、联盟产品、价格），系统会按新配置继续自动运行。
